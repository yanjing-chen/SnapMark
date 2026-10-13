"""Native GTK4/libadwaita screenshot annotation window."""
import io
import math
from pathlib import Path

import cairo
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk

from .model import History, Mark, clamp, fit_zoom
from .paint import paint_document

COLORS = ('#e82c20', '#f66b2d', '#ffbc27', '#26a269', '#3584e4', '#9141ac', '#242424')
TOOLS = (
    ('arrow', '↗', 'Arrow'), ('rectangle', '▭', 'Rectangle'),
    ('ellipse', '◯', 'Ellipse'), ('line', '╱', 'Line'),
    ('pen', '✎', 'Pen'), ('text', 'T', 'Text'),
)


class EditorWindow(Adw.ApplicationWindow):
    def __init__(self, app, filename=None):
        super().__init__(application=app, title='SnapMark', default_width=1200,
                         default_height=790)
        self.set_size_request(580, 440)
        self.filename = None
        self.pixbuf = None
        self.history = History()
        self.preview = None
        self.start_point = None
        self.tool = 'arrow'
        self.color = COLORS[0]
        self.stroke = 4.0
        self.opacity = .25
        self.fill = False
        self.zoom = 1.0
        self._build_ui()
        self._set_actions()
        if filename is not None:
            self.load_image(filename)
        self.present()

    def _build_ui(self):
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        open_btn = self._text_icon_button('Open…', 'document-open-symbolic')
        open_btn.connect('clicked', lambda *_: self.open_dialog())
        header.pack_start(open_btn)

        title = Adw.WindowTitle(title='SnapMark', subtitle='Screenshot Editor')
        header.set_title_widget(title)

        undo_btn = Gtk.Button(icon_name='edit-undo-symbolic', tooltip_text='Undo (Ctrl+Z)')
        undo_btn.connect('clicked', lambda *_: self.undo())
        header.pack_end(self._menu_button())

        save_btn = self._text_icon_button('Save', 'document-save-symbolic')
        save_btn.add_css_class('suggested-action')
        save_btn.connect('clicked', lambda *_: self.save_dialog())
        header.pack_end(save_btn)
        copy_btn = self._text_icon_button('Copy', 'edit-copy-symbolic')
        copy_btn.connect('clicked', lambda *_: self.copy_image())
        header.pack_end(copy_btn)
        redo_btn = Gtk.Button(icon_name='edit-redo-symbolic', tooltip_text='Redo (Ctrl+Shift+Z)')
        redo_btn.connect('clicked', lambda *_: self.redo())
        header.pack_start(undo_btn)
        header.pack_start(redo_btn)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(root)
        toolbar_view.set_content(self._toast_overlay)
        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tools.set_halign(Gtk.Align.CENTER)
        tools.set_margin_top(8)
        tools.set_margin_bottom(8)
        root.append(tools)
        previous = None
        for code, glyph, label in TOOLS:
            button = Gtk.ToggleButton(tooltip_text=label)
            button.add_css_class('flat')
            button.set_size_request(72, 65)
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            icon = Gtk.Label(label=glyph)
            icon.add_css_class('tool-glyph')
            content.append(icon)
            name = Gtk.Label(label=label)
            name.add_css_class('caption')
            content.append(name)
            button.set_child(content)
            if previous is not None:
                button.set_group(previous)
            button.connect('toggled', self._tool_toggled, code)
            tools.append(button)
            if previous is None:
                button.set_active(True)
            previous = button
        root.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        workspace = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        workspace.set_vexpand(True)
        root.append(workspace)

        self.stack = Gtk.Stack()
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        workspace.append(self.stack)

        empty = Adw.StatusPage(title='Ready for a screenshot',
                               description='Take a screenshot with Print Screen, or open an image.',
                               icon_name='image-x-generic-symbolic')
        empty_button = Gtk.Button(label='Open an image…')
        empty_button.add_css_class('suggested-action')
        empty_button.set_halign(Gtk.Align.CENTER)
        empty_button.connect('clicked', lambda *_: self.open_dialog())
        empty.set_child(empty_button)
        self.stack.add_named(empty, 'empty')

        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.scroller.add_css_class('canvas-background')
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_halign(Gtk.Align.START)
        self.canvas.set_valign(Gtk.Align.START)
        self.canvas.set_content_width(800)
        self.canvas.set_content_height(500)
        self.canvas.set_draw_func(self._draw)
        self.scroller.set_child(self.canvas)
        self.stack.add_named(self.scroller, 'document')
        self.stack.set_visible_child_name('empty')

        drag = Gtk.GestureDrag()
        drag.set_button(1)
        drag.connect('drag-begin', self._drag_begin)
        drag.connect('drag-update', self._drag_update)
        drag.connect('drag-end', self._drag_end)
        self.canvas.add_controller(drag)

        self._build_properties(workspace)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        footer.add_css_class('statusbar')
        toolbar_view.add_bottom_bar(footer)
        self.details = Gtk.Label(label='No image')
        self.details.add_css_class('dim-label')
        self.details.set_margin_start(14)
        footer.append(self.details)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        footer.append(spacer)
        minus = Gtk.Button(icon_name='zoom-out-symbolic', tooltip_text='Zoom out')
        minus.add_css_class('flat')
        minus.connect('clicked', lambda *_: self.set_zoom(self.zoom / 1.25))
        footer.append(minus)
        self.zoom_label = Gtk.Label(label='100%')
        self.zoom_label.set_width_chars(5)
        footer.append(self.zoom_label)
        plus = Gtk.Button(icon_name='zoom-in-symbolic', tooltip_text='Zoom in')
        plus.add_css_class('flat')
        plus.connect('clicked', lambda *_: self.set_zoom(self.zoom * 1.25))
        footer.append(plus)
        fit = Gtk.Button(icon_name='zoom-fit-best-symbolic', tooltip_text='Fit to window')
        fit.add_css_class('flat')
        fit.set_margin_end(10)
        fit.connect('clicked', lambda *_: self.fit_image())
        footer.append(fit)

        css = Gtk.CssProvider()
        css.load_from_data(b'''
            .tool-glyph { font-size: 23px; font-weight: 500; }
            .canvas-background { background: alpha(@window_fg_color, 0.055); }
            .properties { border-left: 1px solid alpha(@window_fg_color, 0.09); }
            .statusbar { min-height: 40px; border-top: 1px solid alpha(@window_fg_color, 0.09); }
            .swatch-glyph { font-size: 26px; }
        ''')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                   Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    @staticmethod
    def _text_icon_button(label, icon):
        button = Gtk.Button()
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        content.append(Gtk.Image.new_from_icon_name(icon))
        content.append(Gtk.Label(label=label))
        button.set_child(content)
        return button

    def _menu_button(self):
        menu = Gio.Menu()
        menu.append('Open image…', 'win.open')
        menu.append('Fit to window', 'win.fit')
        menu.append('Actual size', 'win.actual')
        button = Gtk.MenuButton(icon_name='view-more-symbolic', tooltip_text='More options')
        button.set_menu_model(menu)
        return button

    def _build_properties(self, workspace):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        panel.add_css_class('properties')
        panel.set_size_request(258, -1)
        for prop in ('margin-top', 'margin-bottom', 'margin-start', 'margin-end'):
            getattr(panel, f'set_{prop.replace("-", "_")}')(16)
        workspace.append(panel)
        title = Gtk.Label(label='Stroke', xalign=0)
        title.add_css_class('heading')
        panel.append(title)
        label = Gtk.Label(label='Color', xalign=0)
        panel.append(label)
        palette = Gtk.FlowBox()
        palette.set_homogeneous(True)
        palette.set_min_children_per_line(4)
        palette.set_max_children_per_line(4)
        palette.set_selection_mode(Gtk.SelectionMode.NONE)
        panel.append(palette)
        self.color_buttons = []
        previous = None
        for shade in COLORS:
            b = Gtk.ToggleButton(tooltip_text=shade)
            b.add_css_class('flat')
            lab = Gtk.Label()
            lab.set_markup(f'<span foreground="{shade}" size="x-large">●</span>')
            b.set_child(lab)
            if previous:
                b.set_group(previous)
            b.connect('toggled', self._color_toggled, shade)
            palette.insert(b, -1)
            if previous is None:
                b.set_active(True)
            previous = b
            self.color_buttons.append(b)
        self.width_label = Gtk.Label(label='Width · 4 px', xalign=0)
        self.width_label.set_margin_top(14)
        panel.append(self.width_label)
        self.width_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 24, 1)
        self.width_scale.set_value(self.stroke)
        self.width_scale.set_draw_value(False)
        self.width_scale.connect('value-changed', self._width_changed)
        panel.append(self.width_scale)
        panel.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        fill_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        fill_row.append(Gtk.Label(label='Fill shapes'))
        switch = Gtk.Switch()
        switch.set_halign(Gtk.Align.END)
        switch.set_hexpand(True)
        switch.set_valign(Gtk.Align.CENTER)
        switch.connect('notify::active', lambda s, _: setattr(self, 'fill', s.get_active()))
        fill_row.append(switch)
        panel.append(fill_row)
        self.opacity_label = Gtk.Label(label='Fill opacity · 25%', xalign=0)
        panel.append(self.opacity_label)
        opacity_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 5, 100, 5)
        opacity_slider.set_value(25)
        opacity_slider.set_draw_value(False)
        opacity_slider.connect('value-changed', self._opacity_changed)
        panel.append(opacity_slider)

    def _set_actions(self):
        for name, callback in (
            ('open', self.open_dialog), ('fit', self.fit_image), ('actual', lambda: self.set_zoom(1.0)),
            ('undo', self.undo), ('redo', self.redo), ('copy', self.copy_image),
            ('save', self.save_dialog),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', lambda _act, _param, cb=callback: cb())
            self.add_action(action)
        app = self.get_application()
        for name, keys in {
            'open': ['<Control>o'], 'undo': ['<Control>z'],
            'redo': ['<Control><Shift>z', '<Control>y'],
            'copy': ['<Control>c'], 'save': ['<Control>s'],
            'actual': ['<Control>0'],
        }.items():
            app.set_accels_for_action(f'win.{name}', keys)

    def _tool_toggled(self, button, code):
        if button.get_active():
            self.tool = code

    def _color_toggled(self, button, color):
        if button.get_active():
            self.color = color

    def _width_changed(self, scale):
        self.stroke = float(scale.get_value())
        self.width_label.set_text(f'Width · {self.stroke:.0f} px')

    def _opacity_changed(self, scale):
        self.opacity = float(scale.get_value()) / 100
        self.opacity_label.set_text(f'Fill opacity · {self.opacity:.0%}')

    def load_image(self, filename):
        path = Path(filename).expanduser().resolve()
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
        except Exception as exc:
            self._notice(f'Cannot open this image: {exc}')
            return
        self.pixbuf = pixbuf
        self.filename = path
        self.history = History()
        self.preview = None
        self.stack.set_visible_child_name('document')
        self.details.set_text(f'{pixbuf.get_width()} × {pixbuf.get_height()} px')
        GLib.idle_add(self._delayed_fit)

    def _delayed_fit(self):
        self.fit_image()
        return False

    def fit_image(self):
        if not self.pixbuf:
            return
        width = max(self.scroller.get_allocated_width() - 30, 740)
        height = max(self.scroller.get_allocated_height() - 30, 440)
        self.set_zoom(fit_zoom(self.pixbuf.get_width(), self.pixbuf.get_height(),
                               width, height))

    def set_zoom(self, zoom):
        if not self.pixbuf:
            return
        self.zoom = clamp(zoom, .1, 4.0)
        self.canvas.set_content_width(max(1, math.ceil(self.pixbuf.get_width() * self.zoom)))
        self.canvas.set_content_height(max(1, math.ceil(self.pixbuf.get_height() * self.zoom)))
        self.canvas.queue_draw()
        self.zoom_label.set_text(f'{self.zoom:.0%}')

    def _draw(self, _area, cr, _width, _height):
        if not self.pixbuf:
            return
        cr.save()
        cr.scale(self.zoom, self.zoom)
        paint_document(cr, self.pixbuf, self.history.marks, self.preview)
        cr.restore()

    def _pixel(self, x, y):
        return (clamp(x / self.zoom, 0, self.pixbuf.get_width()),
                clamp(y / self.zoom, 0, self.pixbuf.get_height()))

    def _drag_begin(self, gesture, x, y):
        if not self.pixbuf:
            return
        self.start_point = self._pixel(x, y)
        if self.tool == 'text':
            self._prompt_text(x, y)
            self.start_point = None
            return
        sx, sy = self.start_point
        self.preview = Mark(self.tool, sx, sy, sx, sy, self.color, self.stroke,
                            self.fill, self.opacity)
        if self.tool == 'pen':
            self.preview.points.append((sx, sy))

    def _drag_update(self, gesture, dx, dy):
        if not self.preview or not self.start_point:
            return
        ok, sx, sy = gesture.get_start_point()
        if not ok:
            return
        x, y = self._pixel(sx + dx, sy + dy)
        self.preview.x2, self.preview.y2 = x, y
        if self.tool == 'pen':
            if not self.preview.points or self.preview.points[-1] != (x, y):
                self.preview.points.append((x, y))
        self.canvas.queue_draw()

    def _drag_end(self, gesture, dx, dy):
        if self.preview:
            self.history.push(self.preview)
            self.preview = None
            self.canvas.queue_draw()
        self.start_point = None

    def _prompt_text(self, x, y):
        popover = Gtk.Popover()
        popover.set_parent(self.canvas)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        entry = Gtk.Entry(placeholder_text='Type annotation…')
        entry.set_margin_top(12)
        entry.set_margin_bottom(12)
        entry.set_margin_start(12)
        entry.set_margin_end(12)
        popover.set_child(entry)
        px, py = self._pixel(x, y)

        def commit(_entry):
            text = entry.get_text().strip()
            if text:
                self.history.push(Mark('text', px, py, px, py, self.color,
                                       self.stroke, text=text))
                self.canvas.queue_draw()
            popover.popdown()
        entry.connect('activate', commit)
        popover.popup()
        entry.grab_focus()

    def undo(self):
        if self.history.undo():
            self.canvas.queue_draw()

    def redo(self):
        if self.history.redo():
            self.canvas.queue_draw()

    def _render_png(self) -> bytes:
        if not self.pixbuf:
            raise ValueError('No image loaded')
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                     self.pixbuf.get_width(), self.pixbuf.get_height())
        cr = cairo.Context(surface)
        paint_document(cr, self.pixbuf, self.history.marks)
        buffer = io.BytesIO()
        surface.write_to_png(buffer)
        surface.finish()
        return buffer.getvalue()

    def copy_image(self):
        if not self.pixbuf:
            return
        try:
            png = GLib.Bytes.new(self._render_png())
            provider = Gdk.ContentProvider.new_for_bytes('image/png', png)
            if not self.get_display().get_clipboard().set_content(provider):
                self._notice('Failed to copy image')
            else:
                self._notice('Annotated image copied to clipboard')
        except Exception as exc:
            self._notice(f'Cannot copy image: {exc}')

    def save_dialog(self):
        if not self.pixbuf:
            return
        dialog = Gtk.FileDialog(title='Save annotated screenshot')
        stem = self.filename.stem if self.filename else 'Screenshot'
        dialog.set_initial_name(f'{stem}-marked.png')
        dialog.save(self, None, self._save_done)

    def _save_done(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            if not file:
                return
            path = file.get_path()
            if not path:
                self._notice('Choose a local destination')
                return
            Path(path).write_bytes(self._render_png())
            self._notice('Image saved')
        except GLib.Error as exc:
            if 'dismiss' not in exc.message.lower() and 'cancel' not in exc.message.lower():
                self._notice(f'Save failed: {exc.message}')
        except Exception as exc:
            self._notice(f'Save failed: {exc}')

    def open_dialog(self):
        dialog = Gtk.FileDialog(title='Open screenshot')
        image_filter = Gtk.FileFilter()
        image_filter.set_name('Images')
        for name in ('image/png', 'image/jpeg', 'image/webp', 'image/bmp'):
            image_filter.add_mime_type(name)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(image_filter)
        dialog.set_filters(filters)
        dialog.open(self, None, self._open_done)

    def _open_done(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file and file.get_path():
                self.load_image(file.get_path())
        except GLib.Error as exc:
            if 'dismiss' not in exc.message.lower() and 'cancel' not in exc.message.lower():
                self._notice(f'Open failed: {exc.message}')

    def _notice(self, message):
        self._toast_overlay.add_toast(Adw.Toast.new(str(message)))
