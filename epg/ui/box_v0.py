import epg

_SX = "left", "right"
_SY = "top", "bottom"
_SIDES = _SX + _SY

def get_anchor(anchor):
    if anchor in _SIDES:
        return "mid" + anchor
    return anchor

def _get_side_idx(side):
    if side in _SX:
        return 0
    elif side in _SY:
        return 1
    epg._throw(side)

class BaseUISystem:
    @property
    def all_children(self):
        cs = []
        for c in self.children:
            cs.append(c)
            cs.extend(c.all_children)
        return cs

class BaseGM:
    ATTR = {}
    def __init__(self, parent, children):
        self.parent = parent
        self.children = children

        self.init()
        
        self.ATTR.update({"padx":None, "pady":None})
        inner = self.parent.get_inner_rect()
        for box, _kw in children:
            epg._check_attr(_kw, self.ATTR)
            kw = self.ATTR.copy()
            kw.update(_kw)

            self.set_pad(box, kw)
            outer = box.get_outer_rect()
            new_outer = self.map(outer.copy(), inner, kw, box)
            box.size += epg.Vector2(new_outer.size) - outer.size
            box.center = new_outer.center
            
    def adjust(self, outer, occ_rect, kw):
        anchor, fill = kw["anchor"], kw["fill"]
        
        if anchor:
            anchor = get_anchor(anchor)
            setattr(outer, anchor, getattr(occ_rect, anchor))
            
        if fill and fill != "none":
            outer.x = occ_rect.x if fill in ("x", "both") else outer.x
            outer.y = occ_rect.y if fill in ("y", "both") else outer.y
            outer.width = occ_rect.width if fill in ("x", "both") else outer.width
            outer.height = occ_rect.height if fill in ("y", "both") else outer.height

    def set_pad(self, box, kw):
        padx, pady = kw["padx"], kw["pady"]
        if padx or pady:
            if not padx: padx = box.outpad[:2]
            if not pady: pady = box.outpad[2:]
            if isinstance(padx, (int, float)): padx = (padx, padx)
            if isinstance(pady, (int, float)): pady = (pady, pady)
                
            box.outpad = (*padx, *pady)
        
    def init(self):
        pass
    
    def map(self, *_):
        pass

class Pack(BaseGM):
    ATTR = {"side":"top", "anchor":"center", "fill":"none"}
    def map(self, outer, inner, kw, *_):
        si = _get_side_idx(kw["side"])
        inner[si+2] -= outer[si+2] # width
        match kw["side"]:
            case "left":
                occ_rect = inner.x, inner.y, outer.width, inner.height
                inner.x += outer.width
                outer.right = inner.x
            case "right":
                occ_rect = inner.right, inner.y, outer.width, inner.height
                outer.x = inner.right
            case "top":
                occ_rect = inner.x, inner.y, inner.width, outer.height
                inner.y += outer.height
                outer.bottom = inner.y
            case "bottom":
                occ_rect = inner.x, inner.bottom, inner.width, outer.height
                outer.y = inner.bottom

        self.adjust(outer, epg.Rect(occ_rect), kw)
        return outer
    
class Grid(BaseGM):
    ATTR = {"column":0, "row":0, "columnspan":1, "rowspan":1, "anchor":"center", "fill":"none"}
    def init(self):
        self.cols, self.rows = {}, {}
        for key, d, attr, span in (("column", self.cols, "width", "columnspan"),
                             ("row", self.rows, "height", "rowspan")):
            for box, kw_ in self.children:
                kw = self.ATTR.copy()
                kw.update(kw_)
            
                w = getattr(box.get_outer_rect(), attr) // kw[span]
                for i in range(kw[span]):
                    index = kw[key] + i
                    d.setdefault(index, [])
                    d[index].append(w)

            d_ = {k:d[k] for k in sorted(d)}
            d.clear()
            d.update(d_)

    def map(self, outer, inner, kw, *_):
        col, row = kw["column"], kw["row"]
        occ_rect = epg.Rect(
            sum([max(v) if k < col else 0 for k, v in self.cols.items()]) + inner.x,
            sum([max(v) if k < row else 0 for k, v in self.rows.items()]) + inner.y,
            sum([max(self.cols[col+i]) for i in range(kw["columnspan"])]),
            sum([max(self.rows[row+i]) for i in range(kw["rowspan"])])
            )
        self.adjust(outer, occ_rect, kw)
        return outer

class Place(BaseGM):
    ATTR = {"x":None, "y":None, "relx":None, "rely":None, "anchor":"center",
            "width":None, "height":None, "relwidth":None, "relheight":None}
    def map(self, outer, inner, kw, box):
        s = box.size
        if m := kw["width"]:
            outer.width += m - s[0]
        elif m := kw["relwidth"]:
            outer.width += epg.math.round_to_int(inner.width * m) - s[0]
            
        if m := kw["height"]:
            outer.height += m - s[1]
        elif m := kw["relheight"]:
            outer.height += epg.math.round_to_int(inner.height * m) - s[1]

        anchor = get_anchor(kw["anchor"])
        
        if kw["x"] != None and kw["y"] != None:
            setattr(outer, anchor,
                    (inner.x + kw["x"] - box.outpad[0],
                     inner.y + kw["y"] - box.outpad[2])
                    )
        elif kw["relx"] != None and kw["rely"] != None:
            setattr(outer, anchor,
                    (inner.x + epg.math.round_to_int(inner.width * kw["relx"]) - box.outpad[0],
                     inner.y + epg.math.round_to_int(inner.height * kw["rely"]) - box.outpad[2])
                    )
        else:
            epg._throw(t="Miss")

        return outer
    
class Box(epg.Rect, BaseUISystem):
    def __init__(self, parent, size=(0, 0), inpad=0, outpad=0):
        epg.Rect.__init__(self, (0, 0), size)
        self.orig_rect = epg.Rect.copy(self)
        self.inpad = inpad
        self.outpad = outpad
        self.parent = parent
        self._children = [] # Store children boxes and gm kw
        self.unmap()

    def __set_pad(self, attr, arg):
        try:
            arg = int(arg)
        except TypeError:
            length = len(arg)
            if length == 2:
                arg = (arg[0],) * 2 + (arg[1],) * 2
            elif length != 4:
                epg._throw()
        else:
            arg = (arg,) * 4
        setattr(self, attr, arg)

    @property
    def inpad(self):
        return self._inpad
    @inpad.setter
    def inpad(self, arg):
        if arg != None:
            self.__set_pad("_inpad", arg)

    @property
    def outpad(self):
        return self._outpad
    @outpad.setter
    def outpad(self, arg):
        if arg != None:
            self.__set_pad("_outpad", arg)

    @property
    def children(self):
        return [c[0] for c in self._children]
    
    def copy(self):
        box = self.__class__(self.parent, self.size, self.inpad, self.outpad)
        box.topleft = self.topleft
        return box

    def get_inner_rect(self):
        '''Return the rect used to hold the children'''
        p = self.inpad
        return epg.Rect(
            self.x + p[0],
            self.y + p[2],
            self.width - p[0] - p[1],
            self.height - p[2] - p[3]
            )

    def get_outer_rect(self):
        '''Return the rect used to hold itself'''
        p = self.outpad
        return epg.Rect(
            self.x - p[0],
            self.y - p[2],
            self.width + p[0] + p[1],
            self.height + p[2] + p[3]
            )

    def kill(self):
        for c in self.all_children:
            c.kill()
        try:
            self.parent._children.pop(self.parent.children.index(self))
        except ValueError:
            pass

    def resize(self, size):
        self.orig_rect.size = self.size = size

    def map(self, type=None, **kw):
        if self.parent is None:
            epg._throw(f"No need to {type.__name__} the top box", "")
            
        if self.parent.gm and type and self.parent.gm != type:
            epg._throw(f"Cannot use geometry manager \"{type.__name__}\" "\
                      f"because \"{self.parent.gm.__name__}\" is already in use", "")
        elif not (self.parent.gm or type):
            epg._throw("No geometry manager is specified", "")

        if type:
            self.parent.set_gm(type)
        self.parent._children.append((self, kw))

    def unmap(self):
        self.gm = None

    def set_gm(self, type):
        self.gm = type
        
    def pack(self, **kw):
        self.map(Pack, **kw)

    def grid(self, **kw):
        self.map(Grid, **kw)

    def place(self, **kw):
        self.map(Place, **kw)
        
    def update_display(self):
        for c in self.all_children:
            c.update(c.orig_rect)

        if self.gm:
            self.gm(self, self._children)
            
        for c in self.all_children:
            if c.gm:
                c.gm(c, c._children)

class BaseBox(Box):
    def __init__(self, pos=(0, 0), size=None, inpad=0, outpad=0):
        Box.__init__(self, None, size if size else epg.display.get_window_size(), inpad, outpad)
        self.move_ip(pos)

    def kill(self):
        for c in self.all_children:
            c.kill()
