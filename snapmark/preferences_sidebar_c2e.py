"""C2-E: real two-level GTK sidebar; navigation only, never installs models."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from .i18n import _

class PreferencesNavigation(Gtk.ScrolledWindow):
    """Fixed-order core and optional sections; subpages are truly nested."""
    def __init__(self, stack):
        super().__init__()
        self.stack = stack
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_min_content_width(206)
        self.add_css_class('navigation-sidebar')
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        root.set_margin_top(12)
        root.set_margin_bottom(12)
        root.set_margin_start(8)
        root.set_margin_end(8)
        self.set_child(root)
        self.buttons = {}
        for name, label, icon in (
            ('general', 'General', 'preferences-system-symbolic'),
            ('screenshot', 'Screenshots & Annotation', 'image-x-generic-symbolic'),
            ('shortcuts', 'Shortcuts', 'preferences-desktop-keyboard-shortcuts-symbolic'),
        ):
            self._add(root, name, label, icon)
        root.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        self._add(root, 'ai-runtime', 'Local AI Runtime', 'computer-symbolic')
        plugin_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        root.append(plugin_line)
        self._add(plugin_line, 'plugins', 'Plugin Management', 'application-x-addon-symbolic', expand=True)
        arrow = Gtk.ToggleButton(icon_name='pan-down-symbolic', tooltip_text=_('Expand or collapse plugin settings'))
        arrow.add_css_class('flat')
        plugin_line.append(arrow)
        self.submenu = Gtk.Revealer()
        self.submenu.set_reveal_child(True)
        self.submenu.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.submenu.set_transition_duration(150)
        arrow.set_active(True)
        arrow.connect('toggled', lambda b: self.submenu.set_reveal_child(b.get_active()))
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        inner.set_margin_start(21)
        self.submenu.set_child(inner)
        root.append(self.submenu)
        self.plugin_box = inner
        self.plugin_empty = Gtk.Label(label=_('Install and enable plugins to show their settings'), xalign=0)
        self.plugin_empty.add_css_class('dim-label')
        inner.append(self.plugin_empty)
        root.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        self._add(root, 'about', 'About', 'help-about-symbolic')
        # Listen for changes; the editor adds pages after constructing this sidebar.
        stack.connect('notify::visible-child-name', self._highlight)
        self._highlight()

    def _add(self, parent, name, label, icon, expand=False):
        button = Gtk.ToggleButton()
        button.add_css_class('flat')
        button.set_hexpand(expand)
        button.set_halign(Gtk.Align.FILL)
        inside = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        inside.set_margin_start(7)
        inside.set_margin_end(7)
        image = Gtk.Image.new_from_icon_name(icon)
        inside.append(image)
        text = Gtk.Label(label=_(label), xalign=0)
        text.set_hexpand(True)
        inside.append(text)
        button.set_child(inside)
        button.connect('clicked', lambda _b: self._go_to(name))
        parent.append(button)
        self.buttons[name] = button
        return button

    def _go_to(self, name):
        if self.stack.get_visible_child_name() != name:
            self.stack.set_visible_child_name(name)
        # Clicking the current ToggleButton should keep its selected state.
        self._highlight()

    def _highlight(self, *_args):
        name = self.stack.get_visible_child_name()
        for ident, button in self.buttons.items():
            # Let libadwaita style native selection, including readable text
            # in both light and dark themes. Never apply suggested-action here.
            button.set_active(ident == name)

    def populate_plugins(self, registrations):
        """registrations: [(plugin_id, title, symbolic_icon), ...]."""
        for ident in list(self.buttons):
            if ident.startswith('plugin-'):
                widget = self.buttons.pop(ident)
                self.plugin_box.remove(widget)
        visible = 0
        for ident, title, icon in registrations:
            if ident == 'example-settings':
                title = 'Example Settings Plugin'
            page_name = 'plugin-' + ident
            if self.stack.get_child_by_name(page_name) is None:
                continue
            self._add(self.plugin_box, page_name, title, icon)
            visible += 1
        self.plugin_empty.set_visible(visible == 0)
        self._highlight()
