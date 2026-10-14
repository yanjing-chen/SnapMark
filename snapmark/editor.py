"""SnapMark screenshot editor — GTK4/libadwaita, no Qt."""
import io
import math
from copy import deepcopy
from pathlib import Path

import cairo
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango

from .model import History, Mark, clamp, fit_zoom, mark_bounds, resized, translated, update_highlighter_preview
from .paint import hex_rgba, paint_document
from .preferences import Autostart, Settings
from .plugins import PLUGIN_IDS, PluginManager
from .plugin_host import PluginHost, load_plugin

COLORS = ('#e82c20', '#f66b2d', '#ffbc27', '#26a269', '#3584e4', '#9141ac', '#242424')
TOOLS = (
    ('select', 'Select'), ('arrow', 'Arrow'), ('rectangle', 'Rectangle'), ('ellipse', 'Ellipse'),
    ('line', 'Line'), ('triangle', 'Triangle'), ('pen', 'Pen'),
    ('highlighter', 'Highlight'), ('mosaic', 'Mosaic'), ('blur', 'Blur'), ('eraser', 'Eraser'),
    ('text', 'Text'),
)


def draw_tool_icon(_widget, cr, _width, _height, tool):
    """Every tool draws inside the same fixed square; no varying glyph baselines."""
    cr.save()
    cr.set_line_width(1.8)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    # Neutral symbolic icons, including highlighter and blur.
    cr.set_source_rgb(.25, .25, .25)
    if tool == 'select':
        cr.move_to(5, 3); cr.line_to(6, 23); cr.line_to(12, 17)
        cr.line_to(17, 25); cr.line_to(21, 23); cr.line_to(16, 15)
        cr.line_to(24, 13); cr.close_path(); cr.stroke()
    elif tool in ('line', 'arrow'):
        cr.move_to(5, 23)
        cr.line_to(23, 5)
        cr.stroke()
        if tool == 'arrow':
            cr.move_to(15, 5); cr.line_to(23, 5); cr.line_to(23, 13); cr.stroke()
    elif tool == 'rectangle':
        cr.rectangle(5, 8, 19, 13); cr.stroke()
    elif tool == 'ellipse':
        cr.arc(14, 14, 10, 0, math.tau); cr.stroke()
    elif tool == 'triangle':
        cr.move_to(14, 4); cr.line_to(25, 23); cr.line_to(3, 23)
        cr.close_path(); cr.stroke()
    elif tool == 'pen':
        # Sharpened wooden pencil (graphite point, two wooden edges, rear cap).
        cr.move_to(3, 25); cr.line_to(8, 17)
        cr.line_to(22, 3); cr.line_to(26, 7)
        cr.line_to(12, 21); cr.close_path(); cr.stroke()
        cr.move_to(8, 17); cr.line_to(12, 21); cr.stroke()
        cr.move_to(3, 25); cr.line_to(7, 23); cr.stroke()
        cr.move_to(19, 6); cr.line_to(23, 10); cr.stroke()
    elif tool == 'highlighter':
        # Chisel-tip marker silhouette, not a colored painted line.
        cr.move_to(8, 25); cr.line_to(3, 20); cr.line_to(16, 5)
        cr.line_to(23, 10); cr.line_to(10, 25); cr.close_path(); cr.stroke()
        cr.move_to(16, 5); cr.line_to(20, 2); cr.line_to(26, 7)
        cr.line_to(23, 10); cr.stroke()
        cr.move_to(6, 21); cr.line_to(10, 24); cr.stroke()
    elif tool == 'mosaic':
        for y in range(3):
            for x in range(3):
                cr.rectangle(5 + x*7, 5 + y*7, 5, 5)
        cr.fill()
    elif tool == 'blur':
        # Water drop icon for the blur operation.
        cr.move_to(14, 3); cr.curve_to(12, 8, 6, 15, 6, 19)
        cr.curve_to(6, 29, 22, 29, 22, 19)
        cr.curve_to(22, 15, 16, 8, 14, 3)
        cr.close_path(); cr.stroke()
    elif tool == 'eraser':
        cr.move_to(5, 18); cr.line_to(17, 5); cr.line_to(25, 13)
        cr.line_to(13, 25); cr.close_path(); cr.stroke()
    elif tool == 'text':
        cr.set_line_width(2.5)
        cr.move_to(5, 6); cr.line_to(23, 6)
        cr.move_to(14, 6); cr.line_to(14, 24); cr.stroke()
    cr.restore()


class EditorWindow(Adw.ApplicationWindow):
    def __init__(self, app, filename=None):
        super().__init__(application=app, title='SnapMark', default_width=1220,
                         default_height=790)
        self.set_size_request(680, 460)
        self.add_css_class('snapmark-window')
        self.filename = None
        self.pixbuf = None
        self.history = History()
        self.preview = None
        self.start_point = None
        self.tool = 'select'
        self.selected_index = None
        self.edit_preview = None
        self._edit_start_mark = None
        self._edit_mode = None
        self._edit_bounds = None
        self._syncing_controls = False
        self.tool_buttons = {}
        self.settings = Settings()
        self.color_buttons = {}
        self.fill_buttons = {}
        self.color = COLORS[0]
        self.stroke = 4.
        self.highlight_mode = 'freehand'
        self.opacity = .25
        self.fill = False
        self.fill_color = COLORS[0]
        self.font = 'Sans 20'
        self.zoom = 1.
        self._preferences_window = None
        self.plugin_manager = PluginManager()
        self.plugin_host = PluginHost(self)
        self.plugin_errors = []
        self._build_ui()
        for ident in PLUGIN_IDS:
            try:
                load_plugin(self.plugin_manager, ident, self.plugin_host)
            except Exception as exc:
                self.plugin_errors.append(f'{ident}: {exc}')
                print(f'SnapMark: plugin {ident} failed to load: {exc}', flush=True)
        self._set_actions()
        if filename is not None:
            self.load_image(filename)
        self.present()

    def _build_ui(self):
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title='SnapMark', subtitle='Screenshot Editor'))
        toolbar_view.add_top_bar(header)

        undo = Gtk.Button(icon_name='edit-undo-symbolic', tooltip_text='Undo (Ctrl+Z)')
        undo.add_css_class('snapmark-quiet')
        undo.connect('clicked', lambda *_: self.undo())
        redo = Gtk.Button(icon_name='edit-redo-symbolic', tooltip_text='Redo (Ctrl+Shift+Z)')
        redo.add_css_class('snapmark-quiet')
        redo.connect('clicked', lambda *_: self.redo())
        header.pack_start(undo)
        header.pack_start(redo)
        copy = self._text_icon_button('Copy', 'edit-copy-symbolic')
        copy.connect('clicked', lambda *_: self.copy_image())
        save = self._text_icon_button('Save', 'document-save-symbolic')
        # Quiet/transparent button CSS overrode the GNOME blue suggested-action.
        save.remove_css_class('snapmark-quiet')
        save.add_css_class('suggested-action')
        self.save_button = save
        save.connect('clicked', lambda *_: self.save_dialog())
        header.pack_end(self._menu_button())
        header.pack_end(save)
        header.pack_end(copy)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(root)
        toolbar_view.set_content(self._toast_overlay)

        # A horizontally scrollable strip stays aligned on smaller displays.
        tool_scroll = Gtk.ScrolledWindow()
        tool_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        root.append(tool_scroll)
        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        self._plugin_tools = tools
        tools.set_halign(Gtk.Align.CENTER)
        tools.set_margin_top(7)
        tools.set_margin_bottom(7)
        tool_scroll.set_child(tools)
        previous = None
        for code, label in TOOLS:
            button = Gtk.ToggleButton(tooltip_text=label)
            button.add_css_class('snapmark-tool')
            button.set_size_request(73, 64)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            inner.set_valign(Gtk.Align.CENTER)
            inner.set_halign(Gtk.Align.CENTER)
            icon = Gtk.DrawingArea()
            icon.set_content_width(28)
            icon.set_content_height(28)
            icon.set_halign(Gtk.Align.CENTER)
            icon.set_draw_func(draw_tool_icon, code)
            inner.append(icon)
            caption = Gtk.Label(label=label)
            caption.add_css_class('caption')
            caption.set_size_request(68, 19)
            caption.set_xalign(.5)
            inner.append(caption)
            button.set_child(inner)
            if previous is not None:
                button.set_group(previous)
            button.connect('toggled', self._tool_toggled, code)
            tools.append(button)
            self.tool_buttons[code] = button
            if previous is None:
                button.set_active(True)
            previous = button
        root.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.paned.set_wide_handle(True)
        self.paned.set_vexpand(True)
        self.paned.set_resize_start_child(True)
        self.paned.set_resize_end_child(False)
        self.paned.set_shrink_start_child(False)
        self.paned.set_shrink_end_child(False)
        root.append(self.paned)

        self.stack = Gtk.Stack()
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        self._result_split = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self._result_split.set_wide_handle(True)
        self._result_split.set_resize_start_child(True)
        self._result_split.set_resize_end_child(True)
        self._result_split.set_start_child(self.stack)
        self.paned.set_start_child(self._result_split)
        self._plugin_results_stack = None

        empty = Adw.StatusPage(title='Ready for a screenshot',
                               description='Take a screenshot with Print Screen, or open an image.',
                               icon_name='image-x-generic-symbolic')
        button = Gtk.Button(label='Open an image…')
        button.add_css_class('suggested-action')
        button.set_halign(Gtk.Align.CENTER)
        button.connect('clicked', lambda *_: self.open_dialog())
        empty.set_child(button)
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
        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect('pressed', self._canvas_pressed)
        self.canvas.add_controller(click)

        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self._key_pressed)
        self.add_controller(keys)

        self._build_properties()
        # Keep approx. 275 px for properties at the initial window width;
        # GTK4's draggable divider lets the user resize it at any time.
        self.paned.set_position(945)

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
        for icon, tooltip, callback in (
            ('zoom-out-symbolic', 'Zoom out', lambda: self.set_zoom(self.zoom / 1.25)),
            ('zoom-in-symbolic', 'Zoom in', lambda: self.set_zoom(self.zoom * 1.25)),
            ('zoom-fit-best-symbolic', 'Fit to window', self.fit_image),
        ):
            if icon == 'zoom-in-symbolic':
                self.zoom_label = Gtk.Label(label='100%')
                self.zoom_label.set_width_chars(5)
                footer.append(self.zoom_label)
            control = Gtk.Button(icon_name=icon, tooltip_text=tooltip)
            control.add_css_class('flat')
            control.connect('clicked', lambda _b, cb=callback: cb())
            footer.append(control)
            if icon == 'zoom-fit-best-symbolic':
                control.set_margin_end(10)

        css = Gtk.CssProvider()
        css.load_from_data(b'''
            .canvas-background { background: alpha(@window_fg_color, 0.055); }
            .properties { border-left: 1px solid alpha(@window_fg_color, 0.08); }
            .statusbar { min-height: 39px; border-top: 1px solid alpha(@window_fg_color, 0.09); }
            button.snapmark-tool, button.snapmark-quiet {
                background: transparent; background-image: none;
                border: 0; border-image: none; box-shadow: none;
                outline: 0; }
            button.snapmark-tool:checked { background: alpha(@accent_bg_color, 0.16); }
            button.snapmark-tool:hover, button.snapmark-quiet:hover {
                background: alpha(@window_fg_color, 0.065); }
            button.snapmark-tool:focus-visible, button.snapmark-quiet:focus-visible {
                outline: 1px solid @accent_color; outline-offset: -2px; }
            .snapmark-window windowcontrols button { border: 0; box-shadow: none; }
            .palette button { padding: 1px; min-width: 29px; min-height: 29px;
                border: 0; box-shadow: none; }
            button.snapmark-custom-color { padding: 1px; min-width: 29px;
                min-height: 29px; background: transparent; border: 0; box-shadow: none; }
        ''')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                   Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def add_plugin_action(self, ident, label, callback):
        """Official plugin API v1 — add an action without changing built-in tools."""
        button = Gtk.Button(label=label, tooltip_text=f'{ident}: {label}')
        button.add_css_class('snapmark-quiet')
        button.connect('clicked', lambda *_: callback())
        self._plugin_tools.append(button)
        return button

    def add_plugin_result(self, ident, title, builder):
        """Official plugin API v1 — optional results below the screenshot."""
        if self._plugin_results_stack is None:
            self._plugin_results_stack = Gtk.Stack()
            self._plugin_results_stack.set_vexpand(True)
            self._result_split.set_end_child(self._plugin_results_stack)
            self._result_split.set_position(420)
        widget = builder(self)
        self._plugin_results_stack.add_titled(widget, ident, title)
        return widget

    @staticmethod
    def _text_icon_button(label, icon):
        button = Gtk.Button()
        button.add_css_class('snapmark-quiet')
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        content.append(Gtk.Image.new_from_icon_name(icon))
        content.append(Gtk.Label(label=label))
        button.set_child(content)
        return button

    def _menu_button(self):
        menu = Gio.Menu()
        menu.append('Preferences', 'win.preferences')
        button = Gtk.MenuButton(icon_name='view-more-symbolic', tooltip_text='Preferences')
        button.add_css_class('flat')
        button.set_menu_model(menu)
        return button

    def _build_properties(self):
        # Vertical split: style controls above and an actual editable layer list below.
        self.properties_split = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.properties_split.set_wide_handle(True)
        self.properties_split.set_resize_start_child(True)
        self.properties_split.set_resize_end_child(True)
        self.properties_split.set_shrink_start_child(False)
        self.properties_split.set_shrink_end_child(False)
        self.properties_split.set_size_request(246, -1)
        self.properties_split.add_css_class('properties')
        self.paned.set_end_child(self.properties_split)

        side_scroll = Gtk.ScrolledWindow()
        side_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        side_scroll.set_min_content_height(195)
        self.properties_split.set_start_child(side_scroll)
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for prop in ('top', 'bottom', 'start', 'end'):
            getattr(panel, f'set_margin_{prop}')(12)
        side_scroll.set_child(panel)
        title = Gtk.Label(label='Stroke', xalign=0)
        title.add_css_class('heading')
        panel.append(title)
        # Highlight remains ONE toolbar tool; the two stroke styles live in
        # the properties panel immediately BEFORE its color options.
        self.highlight_mode_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.highlight_mode_row.append(Gtk.Label(label='Highlight mode', xalign=0))
        highlight_modes = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.highlight_free_button = Gtk.ToggleButton(label='Freehand')
        self.highlight_line_button = Gtk.ToggleButton(label='Straight line')
        self.highlight_line_button.set_group(self.highlight_free_button)
        self.highlight_free_button.set_hexpand(True)
        self.highlight_line_button.set_hexpand(True)
        self.highlight_free_button.set_active(True)
        self.highlight_free_button.connect('toggled', self._highlight_mode_toggled, 'freehand')
        self.highlight_line_button.connect('toggled', self._highlight_mode_toggled, 'line')
        highlight_modes.append(self.highlight_free_button)
        highlight_modes.append(self.highlight_line_button)
        self.highlight_mode_row.append(highlight_modes)
        self.highlight_mode_row.set_visible(self.tool == 'highlighter')
        panel.append(self.highlight_mode_row)
        panel.append(Gtk.Label(label='Color', xalign=0))
        palette = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)
        palette.add_css_class('palette')
        palette.set_halign(Gtk.Align.START)
        stroke_scroll = Gtk.ScrolledWindow()
        stroke_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        stroke_scroll.set_child(palette)
        panel.append(stroke_scroll)
        previous = None
        for shade in COLORS:
            b = Gtk.ToggleButton(tooltip_text=shade)
            b.add_css_class('flat')
            marker = Gtk.DrawingArea()
            marker.set_content_width(20)
            marker.set_content_height(20)
            marker.set_draw_func(self._swatch_draw, shade)
            b.set_child(marker)
            if previous:
                b.set_group(previous)
            b.connect('toggled', self._color_toggled, shade)
            palette.append(b)
            self.color_buttons[shade] = b
            if previous is None:
                b.set_active(True)
            previous = b

        self.custom_stroke = self._custom_color_button(fill=False)
        palette.append(self.custom_stroke)
        self._add_recent_colors(panel, fill=False)

        self.width_label = Gtk.Label(label='Width · 4 px', xalign=0)
        panel.append(self.width_label)
        self.width_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 24, 1)
        self.width_scale.set_value(self.stroke)
        self.width_scale.set_draw_value(False)
        self.width_scale.connect('value-changed', self._width_changed)
        panel.append(self.width_scale)
        panel.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        fill_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        fill_row.append(Gtk.Label(label='Fill shapes'))
        self.fill_switch = Gtk.Switch()
        self.fill_switch.set_halign(Gtk.Align.END)
        self.fill_switch.set_hexpand(True)
        self.fill_switch.set_valign(Gtk.Align.CENTER)
        self.fill_switch.connect('notify::active', self._fill_changed)
        fill_row.append(self.fill_switch)
        panel.append(fill_row)
        panel.append(Gtk.Label(label='Fill color', xalign=0))
        fill_palette = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)
        fill_palette.add_css_class('palette')
        fill_palette.set_halign(Gtk.Align.START)
        fill_scroll = Gtk.ScrolledWindow()
        fill_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        fill_scroll.set_child(fill_palette)
        panel.append(fill_scroll)
        previous = None
        for shade in COLORS:
            b = Gtk.ToggleButton(tooltip_text=shade)
            b.add_css_class('flat')
            marker = Gtk.DrawingArea()
            marker.set_content_width(20)
            marker.set_content_height(20)
            marker.set_draw_func(self._swatch_draw, shade)
            b.set_child(marker)
            if previous:
                b.set_group(previous)
            b.connect('toggled', self._fill_color_toggled, shade)
            fill_palette.append(b)
            self.fill_buttons[shade] = b
            if previous is None:
                b.set_active(True)
            previous = b
        self.custom_fill = self._custom_color_button(fill=True)
        fill_palette.append(self.custom_fill)

        self.opacity_label = Gtk.Label(label='Opacity · 25%', xalign=0)
        panel.append(self.opacity_label)
        self.opacity_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 5, 100, 5)
        self.opacity_scale.set_value(25)
        self.opacity_scale.set_draw_value(False)
        self.opacity_scale.connect('value-changed', self._opacity_changed)
        panel.append(self.opacity_scale)

        self.font_options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.font_options.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        self.font_options.append(Gtk.Label(label='Text font and size', xalign=0))
        self.font_picker = Gtk.FontDialogButton.new(Gtk.FontDialog())
        self.font_picker.set_font_desc(Pango.FontDescription.from_string(self.font))
        self.font_picker.connect('notify::font-desc', self._font_changed)
        self.font_options.append(self.font_picker)
        self.font_options.set_visible(False)
        panel.append(self.font_options)

        layers_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        layers_box.set_margin_start(10)
        layers_box.set_margin_end(10)
        layers_box.set_margin_top(10)
        layers_box.set_margin_bottom(10)
        self.properties_split.set_end_child(layers_box)
        layer_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        layer_header.append(Gtk.Label(label='Layers', xalign=0, hexpand=True, css_classes=['heading']))
        remove = Gtk.Button(icon_name='user-trash-symbolic', tooltip_text='Delete selected layer (Delete)')
        remove.add_css_class('flat')
        remove.connect('clicked', lambda *_: self.delete_selected())
        layer_header.append(remove)
        layers_box.append(layer_header)
        layer_scroll = Gtk.ScrolledWindow()
        layer_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        layer_scroll.set_vexpand(True)
        self.layers = Gtk.ListBox()
        self.layers.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.layers.add_css_class('boxed-list')
        self._layers_selection_handler = self.layers.connect('row-selected', self._layer_selected)
        layer_scroll.set_child(self.layers)
        layers_box.append(layer_scroll)
        self.layer_hint = Gtk.Label(label='No annotations yet', xalign=0)
        self.layer_hint.add_css_class('dim-label')
        layers_box.append(self.layer_hint)
        self.properties_split.set_position(340)
        self._refresh_layers()

    def _layer_label(self, mark, index):
        if mark.tool == 'text':
            description = 'Text · ' + mark.text.replace('\n', ' ')[:22]
        else:
            description = mark.tool.replace('_', ' ').title()
        return f'{index + 1}. {description}'

    def _refresh_layers(self):
        if not hasattr(self, 'layers'):
            return
        self.layers.handler_block(self._layers_selection_handler)
        while (row := self.layers.get_row_at_index(0)) is not None:
            self.layers.remove(row)
        for index in range(len(self.history.marks) - 1, -1, -1):
            mark = self.history.marks[index]
            row = Gtk.ListBoxRow()
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
            content.set_margin_top(8)
            content.set_margin_bottom(8)
            content.set_margin_start(9)
            content.set_margin_end(9)
            content.append(Gtk.Image.new_from_icon_name('draw-freehand-symbolic'))
            label = Gtk.Label(label=self._layer_label(mark, index), xalign=0,
                              ellipsize=Pango.EllipsizeMode.END, hexpand=True)
            content.append(label)
            row.set_child(content)
            row.set_name(f"snapmark-layer-{index}")
            self.layers.append(row)
            if index == self.selected_index:
                self.layers.select_row(row)
        self.layers.handler_unblock(self._layers_selection_handler)
        self.layer_hint.set_visible(not self.history.marks)

    def _layer_selected(self, _listbox, row):
        if row is not None:
            self.select_layer(int(row.get_name().rsplit("-", 1)[-1]))

    def select_layer(self, index):
        if index is not None and not (0 <= index < len(self.history.marks)):
            index = None
        self.selected_index = index
        self.edit_preview = None
        self._edit_start_mark = None
        if index is not None:
            self.tool_buttons['select'].set_active(True)
            self._sync_selected_properties()
        self._refresh_layers()
        self.canvas.queue_draw()

    def _sync_selected_properties(self):
        mark = self._selected_mark()
        if mark is None:
            return
        self._syncing_controls = True
        try:
            self.color = mark.color
            self._sync_custom_picker(self.custom_stroke, mark.color)
            if mark.color in self.color_buttons:
                self.color_buttons[mark.color].set_active(True)
            self.stroke = mark.width
            self.width_scale.set_value(clamp(mark.width, 1, 24))
            self.fill = mark.fill
            self.fill_switch.set_active(mark.fill)
            self.fill_color = mark.fill_color or mark.color
            self._sync_custom_picker(self.custom_fill, self.fill_color)
            if self.fill_color in self.fill_buttons:
                self.fill_buttons[self.fill_color].set_active(True)
            self.opacity = mark.opacity
            self.opacity_scale.set_value(clamp(mark.opacity * 100, 5, 100))
            self.font = mark.font
            self.font_picker.set_font_desc(Pango.FontDescription.from_string(mark.font))
            self.font_options.set_visible(mark.tool == 'text')
        finally:
            self._syncing_controls = False

    def _selected_mark(self):
        idx = self.selected_index
        return self.history.marks[idx] if idx is not None and 0 <= idx < len(self.history.marks) else None

    def _change_selected(self, **changes):
        if self._syncing_controls or self.tool != 'select':
            return
        original = self._selected_mark()
        if original is None:
            return
        new = deepcopy(original)
        for name, value in changes.items():
            setattr(new, name, value)
        if self.history.replace(self.selected_index, new):
            self.canvas.queue_draw()
            self._refresh_layers()

    def delete_selected(self):
        idx = self.selected_index
        if idx is not None and self.history.delete(idx):
            self.selected_index = None
            self._refresh_layers()
            self.canvas.queue_draw()

    @staticmethod
    def _swatch_draw(_area, cr, _w, _h, color):
        cr.set_source_rgba(*hex_rgba(color))
        cr.arc(11, 11, 9, 0, math.tau)
        cr.fill()

    @staticmethod
    def _rgba_hex(rgba):
        return '#%02x%02x%02x' % tuple(round(max(0., min(1., v)) * 255)
                                        for v in (rgba.red, rgba.green, rgba.blue))

    @staticmethod
    def _custom_color_icon(_area, cr, _width, _height):
        # Four-colour tile instead of the currently selected red swatch.
        for x, y, rgb in ((1, 1, (.89, .17, .13)), (11, 1, (.98, .70, .15)),
                          (1, 11, (.15, .65, .38)), (11, 11, (.21, .52, .91))):
            cr.set_source_rgb(*rgb)
            cr.rectangle(x, y, 9, 9)
            cr.fill()

    def _custom_color_button(self, fill):
        button = Gtk.Button(tooltip_text='More fill colors…' if fill else 'More stroke colors…')
        button.add_css_class('snapmark-custom-color')
        button.add_css_class('flat')
        tile = Gtk.DrawingArea()
        tile.set_content_width(22)
        tile.set_content_height(22)
        tile.set_draw_func(self._custom_color_icon)
        button.set_child(tile)
        button.connect('clicked', lambda *_: self._choose_color(fill))
        return button

    def _choose_color(self, fill):
        dialog = Gtk.ColorDialog(title='Choose a fill color' if fill else 'Choose a stroke color',
                                 with_alpha=False)
        initial = Gdk.RGBA()
        initial.parse(self.fill_color if fill else self.color)
        dialog.choose_rgba(self, initial, None,
                           lambda dlg, result: self._color_chosen(dlg, result, fill))

    def _color_chosen(self, dialog, result, fill):
        try:
            rgba = dialog.choose_rgba_finish(result)
        except GLib.Error as exc:
            # Closing/cancelling the native chooser is not an editing error.
            if 'cancel' not in str(exc).lower() and 'dismiss' not in str(exc).lower():
                self._notice(f'Color selection failed: {exc}')
            return
        if rgba is None:
            return
        color = self._rgba_hex(rgba)
        if fill:
            self.fill_color = color
            self._change_selected(fill_color=color)
        else:
            self.color = color
            self._change_selected(color=color)
        self.settings.remember_color(color)
        self._refresh_recent()

    def _add_recent_colors(self, panel, fill=False):
        if not fill:
            self.recent_panel = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
            self.recent_panel.set_halign(Gtk.Align.START)
            panel.append(self.recent_panel)
            self._refresh_recent()

    def _refresh_recent(self):
        if not hasattr(self, 'recent_panel'):
            return
        while (child := self.recent_panel.get_first_child()) is not None:
            self.recent_panel.remove(child)
        recent = self.settings.recent_colors()
        if recent:
            label = Gtk.Label(label='Recent')
            label.add_css_class('dim-label')
            self.recent_panel.append(label)
            for shade in recent[:5]:
                button = Gtk.Button(tooltip_text=f'Reuse {shade}')
                button.add_css_class('flat')
                icon = Gtk.DrawingArea()
                icon.set_content_width(20)
                icon.set_content_height(20)
                icon.set_draw_func(self._swatch_draw, shade)
                button.set_child(icon)
                button.connect('clicked', lambda _btn, value=shade: self._apply_recent(value))
                self.recent_panel.append(button)

    def _apply_recent(self, color):
        self.color = color
        self._change_selected(color=color)
        self._sync_custom_picker(self.custom_stroke, color)

    def _sync_custom_picker(self, picker, color):
        # The custom picker now has a fixed multicolour tile; keep it neutral.
        if picker is not None:
            picker.set_tooltip_text(f'More colors… (current: {color})')

    def _set_actions(self):
        callbacks = {
            'open': self.open_dialog,
            'fit': self.fit_image,
            'actual': lambda: self.set_zoom(1.),
            'undo': self.undo,
            'redo': self.redo,
            'copy': self.copy_image,
            'save': self.save_dialog,
            'preferences': self.show_preferences,
            'quit': self.get_application().quit,
        }
        for name, callback in callbacks.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', lambda _a, _param, cb=callback: cb())
            self.add_action(action)
        app = self.get_application()
        for name, keys in {
            'open': ['<Control>o'], 'undo': ['<Control>z'],
            'redo': ['<Control><Shift>z', '<Control>y'],
            'copy': ['<Control>c'], 'save': ['<Control>s'],
            'actual': ['<Control>0'],
            'preferences': ['<Control>comma'],
            'quit': ['<Control>q'],
        }.items():
            app.set_accels_for_action(f'win.{name}', keys)

    def _tool_toggled(self, button, code):
        if not button.get_active():
            return
        self.tool = code
        if hasattr(self, 'highlight_mode_row'):
            self.highlight_mode_row.set_visible(code == 'highlighter')
        # The first toggle fires while _build_ui() is still constructing
        # the properties pane. Do not access a widget before it exists.
        if not hasattr(self, 'font_options'):
            return
        selected = self._selected_mark()
        self.font_options.set_visible(
            code == 'text' or (code == 'select' and selected is not None
                               and selected.tool == 'text'))

    def _highlight_mode_toggled(self, button, mode):
        if button.get_active():
            self.highlight_mode = mode

    def _color_toggled(self, button, color):
        if not button.get_active():
            return
        self.color = color
        if hasattr(self, 'custom_stroke'):
            self._change_selected(color=color)
            self._sync_custom_picker(self.custom_stroke, color)

    def _fill_color_toggled(self, button, color):
        if not button.get_active():
            return
        self.fill_color = color
        if hasattr(self, 'custom_fill'):
            self._change_selected(fill_color=color)
            self._sync_custom_picker(self.custom_fill, color)

    def _width_changed(self, scale):
        self.stroke = float(scale.get_value())
        self.width_label.set_text(f'Width · {self.stroke:.0f} px')
        self._change_selected(width=self.stroke)

    def _opacity_changed(self, scale):
        self.opacity = float(scale.get_value()) / 100
        self.opacity_label.set_text(f'Opacity · {self.opacity:.0%}')
        self._change_selected(opacity=self.opacity)

    def _font_changed(self, button, _pspec):
        desc = button.get_font_desc()
        if desc:
            self.font = desc.to_string()
            self._change_selected(font=self.font)

    def _fill_changed(self, switch, _pspec):
        self.fill = switch.get_active()
        self._change_selected(fill=self.fill)

    def _key_pressed(self, _controller, keyval, _keycode, _state):
        if keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace) and self.selected_index is not None:
            self.delete_selected()
            return True
        return False

    def _canvas_pressed(self, _gesture, n_press, x, y):
        if self.tool == 'select' and n_press >= 2:
            index = self.selected_index
            if index is not None and self.history.marks[index].tool == 'text':
                self._prompt_text(x, y, edit_index=index)

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
        self.selected_index = None
        self.edit_preview = None
        self._refresh_layers()
        self.stack.set_visible_child_name('document')
        self.details.set_text(f'{pixbuf.get_width()} × {pixbuf.get_height()} px')
        GLib.idle_add(self._delayed_fit)

    def _delayed_fit(self):
        self.fit_image()
        return False

    def fit_image(self):
        if not self.pixbuf:
            return
        width = max(self.scroller.get_allocated_width() - 30, 200)
        height = max(self.scroller.get_allocated_height() - 30, 180)
        self.set_zoom(fit_zoom(self.pixbuf.get_width(), self.pixbuf.get_height(), width, height))

    def set_zoom(self, zoom):
        if not self.pixbuf:
            return
        self.zoom = clamp(zoom, .1, 4.)
        self.canvas.set_content_width(max(1, math.ceil(self.pixbuf.get_width() * self.zoom)))
        self.canvas.set_content_height(max(1, math.ceil(self.pixbuf.get_height() * self.zoom)))
        self.canvas.queue_draw()
        self.zoom_label.set_text(f'{self.zoom:.0%}')

    def _draw(self, _area, cr, _width, _height):
        if not self.pixbuf:
            return
        cr.save()
        cr.scale(self.zoom, self.zoom)
        # A checkerboard is a canvas aid, never part of the exported PNG.
        cr.save()
        cr.rectangle(0, 0, self.pixbuf.get_width(), self.pixbuf.get_height())
        cr.clip()
        x0, y0, x1, y1 = cr.clip_extents()
        tile = 16
        for gy in range(max(0, int(y0) // tile), min(math.ceil(y1 / tile), math.ceil(self.pixbuf.get_height() / tile))):
            for gx in range(max(0, int(x0) // tile), min(math.ceil(x1 / tile), math.ceil(self.pixbuf.get_width() / tile))):
                if (gx + gy) % 2:
                    cr.set_source_rgb(.84, .84, .84)
                else:
                    cr.set_source_rgb(.97, .97, .97)
                cr.rectangle(gx * tile, gy * tile, tile, tile)
                cr.fill()
        cr.restore()
        marks = self.history.marks
        if self.edit_preview is not None and self.selected_index is not None:
            marks = marks.copy()
            marks[self.selected_index] = self.edit_preview
        paint_document(cr, self.pixbuf, marks, self.preview)
        if self.selected_index is not None and self.selected_index < len(marks):
            self._draw_selection(cr, marks[self.selected_index])
        cr.restore()

    def _draw_selection(self, cr, mark):
        x0, y0, x1, y1 = mark_bounds(mark)
        scale = self.zoom
        cr.save()
        cr.set_source_rgba(.10, .38, .9, 1)
        cr.set_line_width(1.25 / scale)
        cr.set_dash([5 / scale, 4 / scale])
        cr.rectangle(x0, y0, max(1, x1 - x0), max(1, y1 - y0))
        cr.stroke()
        cr.set_dash([])
        handle = 7 / scale
        for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            cr.set_source_rgb(1, 1, 1)
            cr.rectangle(x - handle / 2, y - handle / 2, handle, handle)
            cr.fill_preserve()
            cr.set_source_rgba(.10, .38, .9, 1)
            cr.stroke()
        cr.restore()

    def _selection_handle(self, x, y):
        mark = self._selected_mark()
        if mark is None:
            return None
        x0, y0, x1, y1 = mark_bounds(mark)
        tolerance = 10 / self.zoom
        for handle, hx, hy in (('nw', x0, y0), ('ne', x1, y0),
                               ('sw', x0, y1), ('se', x1, y1)):
            if math.hypot(x - hx, y - hy) <= tolerance:
                return handle
        return None

    @staticmethod
    def _resized_bounds(bounds, handle, dx, dy):
        x0, y0, x1, y1 = bounds
        if 'w' in handle:
            x0 = min(x0 + dx, x1 - 4)
        else:
            x1 = max(x1 + dx, x0 + 4)
        if 'n' in handle:
            y0 = min(y0 + dy, y1 - 4)
        else:
            y1 = max(y1 + dy, y0 + 4)
        return (x0, y0, x1, y1)

    def _pixel(self, x, y):
        return (clamp(x / self.zoom, 0, self.pixbuf.get_width()),
                clamp(y / self.zoom, 0, self.pixbuf.get_height()))

    def _drag_begin(self, gesture, x, y):
        if not self.pixbuf:
            return
        self.start_point = self._pixel(x, y)
        if self.tool == 'select':
            px, py = self.start_point
            handle = self._selection_handle(px, py)
            if handle is None:
                index = self.history.index_at_point(px, py, 8 / self.zoom)
                self.select_layer(index)
            if self.selected_index is not None:
                self._edit_start_mark = deepcopy(self.history.marks[self.selected_index])
                self._edit_bounds = mark_bounds(self._edit_start_mark)
                self._edit_mode = handle or 'move'
            else:
                self._edit_start_mark = None
                self._edit_mode = None
            return
        if self.tool == 'text':
            self._prompt_text(x, y)
            self.start_point = None
            return
        if self.tool == 'eraser':
            sx, sy = self.start_point
            self.preview = Mark('eraser', sx, sy, sx, sy, self.color,
                                self.stroke, points=[(sx, sy)], opacity=1.0)
            self.canvas.queue_draw()
            return
        sx, sy = self.start_point
        self.preview = Mark(self.tool, sx, sy, sx, sy, self.color, self.stroke,
                            self.fill, self.opacity, font=self.font,
                            fill_color=self.fill_color,
                            highlighter_mode=(self.highlight_mode if self.tool == 'highlighter'
                                              else 'freehand'))
        if self.tool in ('pen', 'highlighter'):
            self.preview.points.append((sx, sy))

    def _drag_update(self, gesture, dx, dy):
        if not self.pixbuf or self.start_point is None:
            return
        ok, sx, sy = gesture.get_start_point()
        if not ok:
            return
        x, y = self._pixel(sx + dx, sy + dy)
        if self.tool == 'select':
            if self._edit_start_mark is None:
                return
            px, py = self.start_point
            ddx, ddy = x - px, y - py
            if self._edit_mode == 'move':
                self.edit_preview = translated(self._edit_start_mark, ddx, ddy)
            else:
                bounds = self._resized_bounds(self._edit_bounds, self._edit_mode, ddx, ddy)
                self.edit_preview = resized(self._edit_start_mark, bounds)
            self.canvas.queue_draw()
            return
        if self.tool == 'eraser':
            if self.preview is not None:
                self.preview.x2, self.preview.y2 = x, y
                if self.preview.points[-1] != (x, y):
                    self.preview.points.append((x, y))
                self.canvas.queue_draw()
            return
        if not self.preview:
            return
        self.preview.x2, self.preview.y2 = x, y
        if self.tool == 'highlighter':
            update_highlighter_preview(self.preview, x, y)
        elif self.tool == 'pen':
            if not self.preview.points or self.preview.points[-1] != (x, y):
                self.preview.points.append((x, y))
        self.canvas.queue_draw()

    def _drag_end(self, gesture, dx, dy):
        if self.tool == 'select':
            if self.edit_preview is not None and self.selected_index is not None:
                self.history.replace(self.selected_index, self.edit_preview)
            self.edit_preview = None
            self._edit_start_mark = None
            self._edit_mode = None
            self._refresh_layers()
            self.canvas.queue_draw()
        elif self.tool == 'eraser':
            if self.preview is not None:
                self.history.push(self.preview)
            self.preview = None
            self.selected_index = None
            self._refresh_layers()
            self.canvas.queue_draw()
        elif self.preview:
            if self.history.push(self.preview):
                self.selected_index = None
                self._refresh_layers()
            self.preview = None
            self.canvas.queue_draw()
        self.start_point = None

    def _prompt_text(self, x, y, edit_index=None):
        popover = Gtk.Popover()
        popover.set_parent(self.canvas)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        entry = Gtk.Entry(placeholder_text='Type annotation…')
        if edit_index is not None:
            entry.set_text(self.history.marks[edit_index].text)
        for prop in ('top', 'bottom', 'start', 'end'):
            getattr(entry, f'set_margin_{prop}')(12)
        popover.set_child(entry)
        px, py = self._pixel(x, y)

        def commit(_entry):
            text = entry.get_text().strip()
            if text:
                if edit_index is not None and edit_index < len(self.history.marks):
                    mark = deepcopy(self.history.marks[edit_index])
                    mark.text = text
                    self.history.replace(edit_index, mark)
                    self.selected_index = edit_index
                else:
                    if self.history.push(Mark('text', px, py, px, py, self.color,
                                               self.stroke, text=text, font=self.font)):
                        self.selected_index = None
                self._refresh_layers()
                self.canvas.queue_draw()
            popover.popdown()
            GLib.idle_add(popover.unparent)
        entry.connect('activate', commit)
        popover.popup()
        entry.grab_focus()

    def undo(self):
        if self.history.undo():
            self.selected_index = None
            self._refresh_layers()
            self.canvas.queue_draw()

    def redo(self):
        if self.history.redo():
            self.selected_index = None
            self._refresh_layers()
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
            content = Gdk.ContentProvider.new_for_bytes('image/png', GLib.Bytes.new(self._render_png()))
            if not self.get_display().get_clipboard().set_content(content):
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

    def show_preferences(self):
        if self._preferences_window is not None:
            self._preferences_window.present()
            return
        # PreferencesPage is used for the content, with StackSidebar on the
        # LEFT instead of libadwaita's normal top-of-window page switcher.
        window = Adw.Window(title='SnapMark Preferences', default_width=660,
                            default_height=430, transient_for=self, modal=False)
        window.add_css_class('snapmark-window')
        self._preferences_window = window
        window.connect('close-request', lambda *_: self._forget_preferences())
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        window.set_content(toolbar)
        split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        split.set_resize_start_child(False)
        split.set_shrink_start_child(False)
        split.set_resize_end_child(True)
        split.set_shrink_end_child(False)
        split.set_position(160)
        toolbar.set_content(split)

        stack = Gtk.Stack()
        stack.set_hexpand(True)
        stack.set_vexpand(True)
        sidebar = Gtk.StackSidebar()
        sidebar.set_stack(stack)
        sidebar.set_size_request(145, -1)
        sidebar.add_css_class('navigation-sidebar')
        split.set_start_child(sidebar)
        split.set_end_child(stack)

        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title='General')
        page.add(group)
        stack.add_titled(page, 'general', 'General')
        from .plugin_ui import PluginPreferences
        self._plugin_preferences = PluginPreferences(window, stack)
        from .ai_runtime_ui import AIRuntimePreferences
        self._runtime_preferences = AIRuntimePreferences(window, stack)
        for ident, (title, builder) in self.plugin_host.settings_factories.items():
            plugin_page = builder(self)
            stack.add_titled(plugin_page, 'plugin-' + ident, title)
        autostart = Autostart()
        startup = Adw.SwitchRow(title='Start automatically on login',
                                subtitle='Watch GNOME screenshots in the background')
        startup.set_active(autostart.enabled())
        group.add(startup)
        minimized = Adw.SwitchRow(title='Start minimized',
                                  subtitle='Keep the editor hidden when a status icon is available')
        minimized.set_active(self.settings.start_minimized())
        minimized.connect('notify::active',
                          lambda widget, _pspec: self.settings.set_start_minimized(widget.get_active()))
        group.add(minimized)

        folder = Adw.ActionRow(title='Screenshot folder',
                               subtitle=Settings().screenshot_directory() or 'Automatic (GNOME Screenshots)')
        button = Gtk.Button(label='Choose…')
        button.add_css_class('snapmark-quiet')
        button.set_valign(Gtk.Align.CENTER)
        folder.add_suffix(button)
        reset = Gtk.Button(icon_name='edit-undo-symbolic',
                           tooltip_text='Use automatic screenshot folder')
        reset.add_css_class('snapmark-quiet')
        reset.set_valign(Gtk.Align.CENTER)
        reset.set_sensitive(bool(self.settings.screenshot_directory()))
        folder.add_suffix(reset)
        group.add(folder)

        def toggle_switch(switch, _pspec):
            try:
                autostart.set_enabled(switch.get_active())
                if switch.get_active():
                    self.get_application().start_watching()
                else:
                    self.get_application().stop_watching()
            except (ValueError, OSError) as exc:
                self._notice(str(exc))
                switch.handler_block(toggle_handler)
                switch.set_active(autostart.enabled())
                switch.handler_unblock(toggle_handler)

        toggle_handler = startup.connect('notify::active', toggle_switch)

        def choose_folder(_button):
            dialog = Gtk.FileDialog(title='Choose GNOME screenshot folder')
            dialog.select_folder(window, None, folder_selected)

        def folder_selected(dialog, result):
            try:
                selected = dialog.select_folder_finish(result)
                if selected is None or not selected.get_path():
                    return
                Settings().set_screenshot_directory(selected.get_path())
                folder.set_subtitle(selected.get_path())
                reset.set_sensitive(True)
                self.get_application().refresh_watching()
            except GLib.Error as exc:
                if 'dismiss' not in exc.message.lower() and 'cancel' not in exc.message.lower():
                    self._notice(f'Folder selection failed: {exc.message}')
            except (OSError, ValueError) as exc:
                self._notice(f'Cannot save folder: {exc}')

        def reset_folder(_button):
            try:
                Settings().set_screenshot_directory('')
                folder.set_subtitle('Automatic (GNOME Screenshots)')
                reset.set_sensitive(False)
                self.get_application().refresh_watching()
            except (OSError, ValueError) as exc:
                self._notice(str(exc))

        button.connect('clicked', choose_folder)
        reset.connect('clicked', reset_folder)
        window.present()

    def _forget_preferences(self):
        self._preferences_window = None
        return False

    def _notice(self, message):
        self._toast_overlay.add_toast(Adw.Toast.new(str(message)))
