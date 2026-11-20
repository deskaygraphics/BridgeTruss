"""Geometry presets and mutable model helpers."""


def blank(dim=2):
    return {"dimension": dim, "nodes": {}, "members": {}}


def add_node(m, xyz, fix=None, load=None):
    nid = max(m["nodes"], default=0) + 1
    m["nodes"][nid] = {
        "xyz": list(xyz),
        "fix": list(fix or [False] * 3),
        "load": list(load or [0.0] * 3),
    }
    return nid


def add_member(m, a, b, E=200e9, A=0.005):
    if a not in m["nodes"] or b not in m["nodes"] or a == b:
        raise ValueError("Choose two different existing nodes")
    if any({x["i"], x["j"]} == {a, b} for x in m["members"].values()):
        raise ValueError("Member already exists")
    mid = max(m["members"], default=0) + 1
    m["members"][mid] = {"i": a, "j": b, "E": E, "A": A}
    return mid


def preset(kind="Pratt", dim=2, panels=6, panel_length=4.0, height=4.0, width=3.0):
    """Simply supported single-plane truss; 3D option has two side trusses and cross-bracing."""
    m = blank(dim)
    planes = [0.0] if dim == 2 else [0.0, width]
    for z in planes:
        bottom = []
        top = []
        for i in range(panels + 1):
            bottom.append(add_node(m, [i * panel_length, 0.0, z]))
            top.append(add_node(m, [i * panel_length, height, z]))
        for i in range(panels):
            add_member(m, bottom[i], bottom[i + 1])
            add_member(m, top[i], top[i + 1])
        for i in range(panels + 1):
            add_member(m, bottom[i], top[i])
        for i in range(panels):
            if kind == "Warren":
                a, b = (bottom[i], top[i + 1]) if i % 2 == 0 else (top[i], bottom[i + 1])
            elif kind == "Howe":
                a, b = (bottom[i], top[i + 1]) if i < panels // 2 else (top[i], bottom[i + 1])
            else:  # Pratt diagonals point toward center at the bottom
                a, b = (top[i], bottom[i + 1]) if i < panels // 2 else (bottom[i], top[i + 1])
            add_member(m, a, b)
        # first end pinned in plane, other end roller in x; both restrain vertical
        m["nodes"][bottom[0]]["fix"][:2] = [True, True]
        m["nodes"][bottom[-1]]["fix"][1] = True
        for i in range(1, panels):
            m["nodes"][bottom[i]]["load"][1] = -25000.0 / len(planes)
        if dim == 3:
            # Lateral support of each side's first/last bottom node, and one x restraint only overall.
            m["nodes"][bottom[0]]["fix"][2] = True
            m["nodes"][bottom[-1]]["fix"][2] = True
    if dim == 3:
        n = 2 * (panels + 1)
        for i in range(panels + 1):
            # transverse deck and top ties
            add_member(m, 1 + 2 * i, n + 1 + 2 * i)
            add_member(m, 2 + 2 * i, n + 2 + 2 * i)
        for i in range(panels):
            # X bracing in horizontal top and bottom planes
            add_member(m, 1 + 2 * i, n + 1 + 2 * (i + 1))
            add_member(m, n + 1 + 2 * i, 1 + 2 * (i + 1))
            add_member(m, 2 + 2 * i, n + 2 + 2 * (i + 1))
            add_member(m, n + 2 + 2 * i, 2 + 2 * (i + 1))
        # a transverse x restraint on the second side is not needed; first side provides x reference.
    return m
