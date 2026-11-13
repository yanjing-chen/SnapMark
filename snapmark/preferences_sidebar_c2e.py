"""SnapMark native GTK4 preferences sidebar: no plugin or runtime sections."""
from gi.repository import Gtk
from .i18n import _

class PreferencesNavigation(Gtk.ScrolledWindow):
    def __init__(self, stack):
        super().__init__()
        self.stack = stack
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_min_content_width(206)
        self.add_css_class('navigation-sidebar')
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(root, f'set_margin_{side}')(10)
        self.set_child(root)
        self.buttons = {}
        for ident, label, icon in (
            ('general', 'General', 'preferences-system-symbolic'),
            ('screenshot', 'Screenshots & Annotation', 'image-x-generic-symbolic'),
            ('shortcuts', 'Shortcuts', 'preferences-desktop-keyboard-shortcuts-symbolic'),
            ('ocr', 'OCR', 'edit-find-symbolic'),
            ('about', 'About', 'help-about-symbolic'),
        ):
            row = Gtk.ToggleButton()
            row.add_css_class('flat')
            row.set_halign(Gtk.Align.FILL)
            inside = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
            inside.append(Gtk.Image.new_from_icon_name(icon))
            label_widget = Gtk.Label(label=_(label), xalign=0)
            label_widget.set_hexpand(True)
            inside.append(label_widget)
            row.set_child(inside)
            row.connect('clicked', lambda _b, key=ident: self._go_to(key))
            root.append(row)
            self.buttons[ident] = row
        stack.connect('notify::visible-child-name', self._highlight)
        self._highlight()

    def _go_to(self, ident):
        if self.stack.get_visible_child_name() != ident:
            self.stack.set_visible_child_name(ident)
        self._highlight()

    def _highlight(self, *_args):
        current = self.stack.get_visible_child_name()
        for ident, button in self.buttons.items():
            button.set_active(ident == current)
