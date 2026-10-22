"""Scrollable unverified streaming preview for OCR and translation.

Only a finished and validated result enters the editable result TextView.  GTK
may recompute TextView geometry over several frames: those geometry-driven
adjustment changes are not the user's request to stop following new text.
"""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, GLib, Gdk


class StreamingPreview:
    def __init__(self, stack):
        # GTK emits Adjustment::changed while child widgets are still being
        # constructed. Initialize every callback-visible field first.
        self.stack = stack
        self.follow = True
        self._updating = False
        self._bar_down = False
        self._text = ''
        self._follow_source = 0
        self._follow_attempts = 0
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_min_content_height(110)
        self.scroller.set_vexpand(True)
        self.view = Gtk.TextView()
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_editable(False)
        self.view.set_cursor_visible(False)
        self.view.set_can_focus(True)
        for side in ('top', 'bottom', 'left', 'right'):
            getattr(self.view, f'set_{side}_margin')(8)
        self.buffer = self.view.get_buffer()
        self.end_mark = self.buffer.create_mark(None, self.buffer.get_end_iter(), False)
        self.scroller.set_child(self.view)
        self.stack.add_named(self.scroller, 'stream')

        self.adjustment = self.scroller.get_vadjustment()
        # The Adjustment is also updated by GTK's asynchronous text reflow.
        # Treat only *explicit input* as a request to stop following.
        self.adjustment.connect('value-changed', self._on_adjustment_value)
        self.adjustment.connect('changed', self._on_adjustment_changed)
        # GTK4 Gtk.Scrollbar is no longer a Gtk.Range: it has no
        # "change-value" signal (connecting it crashed the native test).
        # Observe user presses with GTK4 GestureClick while leaving the
        # native scrollbar implementation in full control of dragging.
        bar = self.scroller.get_vscrollbar()
        if bar is not None:
            self.bar_gesture = Gtk.GestureClick.new()
            self.bar_gesture.set_button(0)
            self.bar_gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            self.bar_gesture.connect('pressed', self._on_bar_pressed)
            self.bar_gesture.connect('released', self._on_bar_released)
            bar.add_controller(self.bar_gesture)

        controller = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        controller.connect('scroll', self._wheel_scroll)
        self.scroller.add_controller(controller)
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect('key-pressed', self._on_key)
        self.view.add_controller(key_controller)

    def _at_bottom(self):
        a = self.adjustment
        return a.get_value() >= max(0, a.get_upper() - a.get_page_size() - 12)

    def _on_adjustment_value(self, *_args):
        # A scroll that GTK initiates after a resize is not a user gesture.
        # While following, continue following. When paused, detect a user
        # returning to the bottom using any scrolling mechanism.
        if not self.follow and not self._updating and not self._bar_down:
            self._on_scroll()

    def _on_adjustment_changed(self, *_args):
        # Includes size changes after GTK has rewrapped/increased the text.
        if self.follow and self.stack.get_visible_child_name() == 'stream':
            self._queue_follow()

    def _on_scroll(self, *_args):
        # Kept as a distinct behavior hook for testability and compatibility.
        if not self._updating:
            self.follow = self._at_bottom()
            if self.follow:
                self._queue_follow()

    def _pause_follow(self):
        self.follow = False
        self._updating = False
        if self._follow_source:
            GLib.source_remove(self._follow_source)
            self._follow_source = 0

    def _on_bar_pressed(self, _gesture, _n_press, _x, _y):
        # Distinguish actual scrollbar input from GTK's own reflow.
        self._bar_down = True
        self._pause_follow()

    def _on_bar_released(self, _gesture, _n_press, _x, _y):
        self._bar_down = False
        # The adjustment is applied asynchronously at the end of a drag.
        GLib.timeout_add(40, self._recheck_bottom)

    def _wheel_scroll(self, _controller, _dx, dy):
        if dy < 0:
            self._pause_follow()
        elif dy > 0:
            GLib.timeout_add(30, self._recheck_bottom)
        return False

    def _on_key(self, _controller, keyval, _keycode, _state):
        if keyval in (Gdk.KEY_Up, Gdk.KEY_Page_Up, Gdk.KEY_Home):
            self._pause_follow()
        elif keyval in (Gdk.KEY_Down, Gdk.KEY_Page_Down, Gdk.KEY_End):
            GLib.timeout_add(30, self._recheck_bottom)
        return False

    def _recheck_bottom(self):
        if not self._bar_down and self._at_bottom():
            self.follow = True
            self._queue_follow()
        return False

    def _scroll_bottom(self):
        self._follow_source = 0
        if not self.follow or self.stack.get_visible_child_name() != 'stream':
            self._updating = False
            return False
        # TextView's layout can lag buffer insertion; place its end mark at
        # the lower edge and also clamp the ScrolledWindow adjustment.
        self.view.scroll_mark_onscreen(self.end_mark)
        self.view.scroll_to_mark(self.end_mark, 0.0, True, 0.0, 1.0)
        a = self.adjustment
        a.set_value(max(0, a.get_upper() - a.get_page_size()))
        if not self._at_bottom() and self._follow_attempts < 30:
            self._follow_attempts += 1
            self._queue_follow()
        else:
            self._updating = False
        return False

    def _queue_follow(self):
        if self.follow and not self._follow_source:
            self._updating = True
            self._follow_source = GLib.timeout_add(25, self._scroll_bottom)

    def set_visible(self, visible):
        self.stack.set_visible_child_name('stream' if visible else 'result')
        if visible and self.follow:
            self._follow_attempts = 0
            self._queue_follow()
        elif not visible and self._follow_source:
            GLib.source_remove(self._follow_source)
            self._follow_source = 0
            self._updating = False

    def start(self):
        self.follow = True
        self._text = ''
        self._follow_attempts = 0
        self._updating = True
        self.buffer.set_text('')
        self.set_visible(True)

    def set_text(self, text):
        if not isinstance(text, str):
            return
        should_follow = self.follow
        self._updating = True
        if text.startswith(self._text):
            suffix = text[len(self._text):]
            if suffix:
                self.buffer.insert(self.buffer.get_end_iter(), suffix)
        else:
            self.buffer.set_text(text)
        self._text = text
        if should_follow:
            self._follow_attempts = 0
            self._queue_follow()
        else:
            self._updating = False

    def get_text(self):
        return self._text
