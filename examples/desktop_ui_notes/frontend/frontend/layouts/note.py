from patera.desktop.ui import Component, layout, tag, template


@layout
@tag("note-layout")
class NoteLayout(Component):
    def markup(self):
        return template(
            '<section class="note-layout"><div id="note-content"></div></section>'
        )
