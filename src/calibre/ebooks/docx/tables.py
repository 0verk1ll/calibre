#!/usr/bin/env python
# vim:fileencoding=utf-8
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__ = 'GPL v3'
__copyright__ = '2013, Kovid Goyal <kovid at kovidgoyal.net>'

from collections import OrderedDict

from lxml.html.builder import TABLE, TR, TD

from calibre.ebooks.docx.block_styles import inherit, read_shd, read_border, binary_property, border_props, ParagraphStyle  # noqa
from calibre.ebooks.docx.char_styles import RunStyle
from calibre.ebooks.docx.names import XPath, get, is_tag

# Read from XML {{{
def _read_width(elem):
    ans = inherit
    try:
        w = int(get(elem, 'w:w'))
    except (TypeError, ValueError):
        w = 0
    typ = get(elem, 'w:type', 'auto')
    if typ == 'nil':
        ans = '0'
    elif typ == 'auto':
        ans = 'auto'
    elif typ == 'dxa':
        ans = '%.3gpt' % (w/20)
    elif typ == 'pct':
        ans = '%.3g%%' % (w/50)
    return ans

def read_width(parent, dest):
    ans = inherit
    for tblW in XPath('./w:tblW')(parent):
        ans = _read_width(tblW)
    setattr(dest, 'width', ans)

def read_cell_width(parent, dest):
    ans = inherit
    for tblW in XPath('./w:tcW')(parent):
        ans = _read_width(tblW)
    setattr(dest, 'width', ans)

def read_padding(parent, dest):
    name = 'tblCellMar' if parent.tag.endswith('}tblPr') else 'tcMar'
    left = top = bottom = right = inherit
    for mar in XPath('./w:%s' % name)(parent):
        for x in ('left', 'top', 'right', 'bottom'):
            for edge in XPath('./w:%s' % x)(mar):
                locals()[x] = _read_width(edge)
    for x in ('left', 'top', 'right', 'bottom'):
        setattr(dest, 'cell_padding_%s' % x, locals()[x])

def read_justification(parent, dest):
    left = right = inherit
    for jc in XPath('./w:jc[@w:val]')(parent):
        val = get(jc, 'w:val')
        if not val:
            continue
        if val == 'left':
            right = 'auto'
        elif val == 'right':
            left = 'auto'
        elif val == 'center':
            left = right = 'auto'
    setattr(dest, 'margin_left', left)
    setattr(dest, 'margin_right', right)

def read_spacing(parent, dest):
    ans = inherit
    for cs in XPath('./w:tblCellSpacing')(parent):
        ans = _read_width(cs)
    setattr(dest, 'spacing', ans)

def read_indent(parent, dest):
    ans = inherit
    for cs in XPath('./w:tblInd')(parent):
        ans = _read_width(cs)
    setattr(dest, 'indent', ans)

border_edges = ('left', 'top', 'right', 'bottom', 'insideH', 'insideV')

def read_borders(parent, dest):
    name = 'tblBorders' if parent.tag.endswith('}tblPr') else 'tcBorders'
    read_border(parent, dest, border_edges, name)

def read_height(parent, dest):
    ans = inherit
    for rh in XPath('./w:trHeight')(parent):
        rule = get(rh, 'w:hRule', 'auto')
        if rule in {'auto', 'atLeast', 'exact'}:
            val = get(rh, 'w:val')
            ans = (rule, val)
    setattr(dest, 'height', ans)

def read_vertical_align(parent, dest):
    ans = inherit
    for va in XPath('./w:vAlign')(parent):
        val = get(va, 'w:val')
        ans = {'center': 'middle', 'top': 'top', 'bottom': 'bottom'}.get(val, 'middle')
    setattr(dest, 'vertical_align', ans)

def read_col_span(parent, dest):
    ans = inherit
    for gs in XPath('./w:gridSpan')(parent):
        try:
            ans = int(get(gs, 'w:val'))
        except (TypeError, ValueError):
            continue
    setattr(dest, 'col_span', ans)

def read_merge(parent, dest):
    for x in ('hMerge', 'vMerge'):
        ans = inherit
        for m in XPath('./w:%s' % x)(parent):
            ans = get(m, 'w:val', 'continue')
        setattr(dest, x, ans)

def read_band_size(parent, dest):
    for x in ('Col', 'Row'):
        ans = 1
        for y in XPath('./w:tblStyle%sBandSize' % x)(parent):
            try:
                ans = int(get(y, 'w:val'))
            except (TypeError, ValueError):
                continue
        setattr(dest, '%s_band_size' % x.lower(), ans)

def read_look(parent, dest):
    ans = 0
    for x in XPath('./w:tblLook')(parent):
        try:
            ans = int(get(x, 'w:val'), 16)
        except (ValueError, TypeError):
            continue
    setattr(dest, 'look', ans)

# }}}

class RowStyle(object):

    all_properties = ('height', 'cantSplit', 'hidden', 'spacing',)

    def __init__(self, tcPr=None):
        if tcPr is None:
            for p in self.all_properties:
                setattr(self, p, inherit)
        else:
            pass

class CellStyle(object):

    all_properties = ('background_color', 'cell_padding_left', 'cell_padding_right', 'cell_padding_top',
        'cell_padding_bottom', 'width', 'vertical_align', 'col_span', 'vMerge', 'hMerge',
    ) + tuple(k % edge for edge in border_edges for k in border_props)

    def __init__(self, trPr=None):
        if trPr is None:
            for p in self.all_properties:
                setattr(self, p, inherit)
        else:
            for x in ('borders', 'shd', 'padding', 'cell_width', 'vertical_align', 'col_span', 'merge'):
                f = globals()['read_%s' % x]
                f(trPr, self)

class TableStyle(object):

    all_properties = (
        'width', 'cell_padding_left', 'cell_padding_right', 'cell_padding_top',
        'cell_padding_bottom', 'margin_left', 'margin_right', 'background_color',
        'spacing', 'indent', 'overrides', 'col_band_size', 'row_band_size', 'look',
    ) + tuple(k % edge for edge in border_edges for k in border_props)

    def __init__(self, tblPr=None):
        if tblPr is None:
            for p in self.all_properties:
                setattr(self, p, inherit)
        else:
            self.overrides = inherit
            for x in ('width', 'padding', 'shd', 'justification', 'spacing', 'indent', 'borders', 'band_size', 'look'):
                f = globals()['read_%s' % x]
                f(tblPr, self)
            parent = tblPr.getparent()
            if is_tag(parent, 'w:style'):
                self.overrides = {}
                for tblStylePr in XPath('./w:tblStylePr[@w:type]')(parent):
                    otype = get(tblStylePr, 'w:type')
                    orides = self.overrides[otype] = {}
                    for tblPr in XPath('./w:tblPr')(tblStylePr):
                        orides['table'] = TableStyle(tblPr)
                    for trPr in XPath('./w:trPr')(tblStylePr):
                        orides['row'] = RowStyle(trPr)
                    for tcPr in XPath('./w:tcPr')(tblStylePr):
                        orides['cell'] = tcPr
                    for pPr in XPath('./w:pPr')(tblStylePr):
                        orides['block'] = ParagraphStyle(pPr)
                    for rPr in XPath('./w:rPr')(tblStylePr):
                        orides['char'] = RunStyle(rPr)

    def update(self, other):
        for prop in self.all_properties:
            nval = getattr(other, prop)
            if nval is not inherit:
                setattr(self, prop, nval)

    def resolve_based_on(self, parent):
        for p in self.all_properties:
            val = getattr(self, p)
            if val is inherit:
                setattr(self, p, getattr(parent, p))


class Tables(object):

    def __init__(self):
        self.tables = OrderedDict()

    def register(self, tbl):
        self.tables[tbl] = self.current_table = []

    def add(self, p):
        self.current_table.append(p)

    def apply_markup(self, object_map):
        rmap = {v:k for k, v in object_map.iteritems()}
        for tbl, blocks in self.tables.iteritems():
            if not blocks:
                continue
            parent = rmap[blocks[0]].getparent()
            table = TABLE('\n\t\t')
            idx = parent.index(rmap[blocks[0]])
            parent.insert(idx, table)
            for row in XPath('./w:tr')(tbl):
                tr = TR('\n\t\t\t')
                tr.tail = '\n\t\t'
                table.append(tr)
                for tc in XPath('./w:tc')(row):
                    td = TD()
                    td.tail = '\n\t\t\t'
                    tr.append(td)
                    for p in XPath('./w:p')(tc):
                        block = rmap[p]
                        td.append(block)
                if len(tr):
                    tr[-1].tail = '\n\t\t'
            if len(table):
                table[-1].tail = '\n\t'


