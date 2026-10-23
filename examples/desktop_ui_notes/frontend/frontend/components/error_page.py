from patera.desktop.ui import Component, tag, template


@tag("notes-error")
class ErrorPage(Component):
    def markup(self):
        return template(
            "<h1>Unable to open this page</h1><p>{{ args.message }}</p>"
            "<a href=\"{{ app.url_for('NotesHome') }}\">Back to notes</a>"
        )
