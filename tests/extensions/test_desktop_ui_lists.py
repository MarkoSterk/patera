"""Portable keyed/virtual rendering contracts, without a browser."""

from types import SimpleNamespace

import pytest

from patera.desktop.ui import TemplateEngine, template
from patera.desktop.ui.lists import window_bounds


def test_keyed_blocks_refresh_and_validate_atomically():
    state = SimpleNamespace(rows=[dict(id="a", title="A"), dict(id="b", title="B")])
    _, rendered = TemplateEngine().render(
        template(
            """{% keyed "rows" %}
        {% for row in state.rows %}<li data-ui-key="{{row.id}}">{{row.title}}</li>{% endfor %}
        {% endkeyed %}""",
            state=state,
        )
    )
    assert rendered.modes == {"1": "keyed"}
    state.rows.reverse()
    changed = rendered.refresh("rows")
    assert changed[0][1].index('data-ui-key="b"') < changed[0][1].index(
        'data-ui-key="a"'
    )
    previous = dict(rendered.outputs)
    state.rows.append(state.rows[0])
    with pytest.raises(ValueError, match="unique"):
        rendered.refresh("rows")
    assert rendered.outputs == previous
    assert rendered.stack == []


@pytest.mark.parametrize(
    "source",
    [
        '{% keyed "rows" %}<div>missing key</div>{% endkeyed %}',
        '{% keyed "rows" %}bare text{% endkeyed %}',
        '{% keyed "rows" %}<div data-ui-key="a"><div data-ui-key="b">{% endkeyed %}',
        '{% keyed "rows" %}<div data-ui-key="a"></div><div data-ui-key="a"></div>{% endkeyed %}',
    ],
)
def test_invalid_keyed_rows_are_rejected_on_initial_render(source):
    with pytest.raises(ValueError):
        TemplateEngine().render(template(source))


def test_virtual_only_evaluates_window_and_reloads_replaced_source():
    visited = []
    state = SimpleNamespace(rows=[dict(id=i, title=f"Row {i}") for i in range(10000)])
    engine = TemplateEngine(
        filters={"visit": lambda item: visited.append(item) or item}
    )
    markup, rendered = engine.render(
        template(
            """{% virtual "rows", state.rows, key="id", row_height=20, height=100, overscan=2 %}
        <b>{{item.title|visit}}</b><span>{{index}}</span>
        {% endvirtual %}""",
            state=state,
        )
    )
    assert len(visited) == 7
    assert 'aria-setsize="10000"' in markup
    assert rendered.modes == {"1": "virtual"}
    visited.clear()
    rendered.virtual_offsets["1"] = 2000
    change = rendered.refresh("rows")[0][1]
    assert visited == [f"Row {i}" for i in range(98, 107)]
    assert "height:1960px" in change
    state.rows = [dict(id="<new>", title="<escaped>")]
    change = rendered.refresh("rows")[0][1]
    assert 'data-ui-key="&lt;new&gt;"' in change
    assert "&lt;escaped&gt;" in change
    assert rendered.virtual_offsets["1"] == 0
    assert len(rendered.fragments) == 1
    state.rows = []
    assert "data-ui-key=" not in rendered.refresh("rows")[0][1]


def test_virtual_nested_bindings_keep_current_loop_locals_and_no_obsolete_rows():
    state = SimpleNamespace(rows=[dict(id=i, value=i) for i in range(100)])
    _, rendered = TemplateEngine().render(
        template(
            """{% virtual "rows", state.rows, row_height=20, height=40, overscan=0 %}
      <b data-bind="value">{{item.value}}</b>{% endvirtual %}""",
            state=state,
        )
    )
    assert len(rendered.fragments) == 3
    rendered.virtual_offsets["1"] = 1000
    rendered.refresh("rows")
    assert [value for _, value in rendered.refresh("value")] == ["50", "51"]
    assert len(rendered.fragments) == 3


def test_virtual_duplicate_keys_outside_window_are_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        TemplateEngine().render(
            template(
                """{% virtual "rows", items, height=10, overscan=0 %}{{item.id}}{% endvirtual %}""",
                items=[dict(id=1), dict(id=2), dict(id=1)],
            )
        )


def test_virtual_window_boundaries():
    assert window_bounds(100, 50000, 20, 100, 2) == (93, 100, 1900)
    assert window_bounds(0, 50000, 20, 100, 2) == (0, 0, 0)
    assert window_bounds(3, -30, 20, 100, 2) == (0, 3, 0)
    for row_height, height, overscan in [
        (0, 100, 1),
        (20, float("nan"), 1),
        (20, 100, -1),
    ]:
        with pytest.raises(ValueError):
            window_bounds(100, 0, row_height, height, overscan)


def test_keyed_rejects_mismatched_html_and_nested_lists():
    for source in (
        '{% keyed "a" %}<div data-ui-key="1"><b></div></b>{% endkeyed %}',
        '{% keyed "a" %}<div data-ui-key="1"/>{% endkeyed %}',
        '{% keyed "a" %}<div data-ui-key="1">{% keyed "b" %}{% endkeyed %}</div>{% endkeyed %}',
    ):
        with pytest.raises(ValueError):
            TemplateEngine().render(template(source))


def test_virtual_callable_key_and_options_validation():
    markup, _ = TemplateEngine().render(
        template(
            '{% virtual "items", items, key=identify, row_height=10, height=20, overscan=0 %}{{item}}{% endvirtual %}',
            items=["a", "b", "c"],
            identify=lambda item: item.upper(),
        )
    )
    assert 'data-ui-key="A"' in markup
    assert 'data-ui-key="C"' not in markup
    with pytest.raises(ValueError):
        window_bounds(1, 0, True, 20, 0)
