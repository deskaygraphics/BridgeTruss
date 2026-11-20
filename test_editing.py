from copy import deepcopy
import pytest
from bridge_model import Model
from editing import member_edit, load_edit


@pytest.mark.parametrize(
    "a,b,area,E",
    [
        (0, 0, 0.01, 2e11),
        (0, 99, 0.01, 2e11),
        (0, 2, -1, 2e11),
        (0, 2, 0.01, float("nan")),
        (0, 1, 0.01, 2e11),
    ],
)
def test_invalid_edit_is_atomic(a, b, area, E):
    m = Model()
    before = deepcopy(m.members)
    with pytest.raises(ValueError):
        member_edit(m, a, b, area, E)
    assert m.members == before


def test_attach_reconnect_and_load_reassignment():
    m = Model()
    member_edit(m, 0, 2, 0.01, 2e11)
    assert len(m.members) == 18
    member_edit(m, 0, 3, 0.02, 1e11, 17)
    assert (m.members[-1].a, m.members[-1].b, m.members[-1].A) == (0, 3, 0.02)
    load_edit(m, 6, 1, 2000, -4000)
    assert 6 not in m.loads and m.loads[1] == (2000, -4000)
    load_edit(m, 1, 1, 0, 0)
    assert 1 not in m.loads
    before = dict(m.loads)
    with pytest.raises(ValueError):
        load_edit(m, 7, 99, 0, -1)
    assert m.loads == before
