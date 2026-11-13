"""Read-only gallery of GNOME's existing screenshot folders.

No clipboard monitoring, screenshot copying, SQLite, or new screenshot engine.
"""
from pathlib import Path
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk, Pango
from .screenshot_paths import IMAGE_SUFFIXES, is_screenshot_folder
from .preferences import Settings
from .i18n import _


def history_paths(pictures, configured='', home=None, limit=200):
    """List GNOME screenshots. A chosen folder is authoritative, regardless of language.

    Automatic mode uses the localized XDG Pictures directory supplied by GLib,
    with known GNOME screenshot subfolders; it never scans arbitrary image folders.
    """
    pictures = Path(pictures).expanduser()
    home = Path(home).expanduser() if home else Path.home()
    explicit = bool(configured)
    if explicit:
        roots = [Path(configured).expanduser()]
    else:
        roots = [pictures / 'Screenshots', pictures / '截图', pictures / '屏幕截图',
                 home / 'Pictures' / 'Screenshots', home / '图片' / '截图']
        try:
            roots.extend(p for p in pictures.iterdir()
                         if p.is_dir() and is_screenshot_folder(p.name))
        except OSError:
            pass
    files = {}
    for folder in roots:
        try:
            folder = folder.resolve(strict=False)
            if not folder.is_dir():
                continue
            if not explicit and not is_screenshot_folder(folder.name):
                continue
            for image in folder.iterdir():
                if image.is_symlink() or not image.is_file() or image.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                files[image] = image.stat().st_mtime_ns
        except (OSError, PermissionError):
            continue
    return sorted(files, key=lambda p: (files[p], p.name), reverse=True)[:limit]


# The thumbnail may show a *preview-only* crop of uniform empty margins.
# It never changes the saved file or the image passed to the editor.
def _content_bounds_rgb(pixels, width, height, stride, channels):
    """Find visually meaningful content inside a nearly uniform border.

    Returns (x, y, width, height) or None when content-aware cropping is unsafe.
    Uses a coarse scan of an already downscaled image to bound memory/CPU usage.
    """
    if width < 24 or height < 24 or channels < 3:
        return None
    def color(x, y):
        pos = y * stride + x * channels
        return (pixels[pos], pixels[pos + 1], pixels[pos + 2])
    corners = [color(x, y) for x, y in
               ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1))]
    background = tuple(sum(c[i] for c in corners) // 4 for i in range(3))
    if any(max(abs(c[i] - background[i]) for i in range(3)) > 28 for c in corners):
        return None
    step = max(1, min(width, height) // 90)
    xmin, ymin, xmax, ymax = width, height, -1, -1
    count = 0
    for y in range(0, height, step):
        for x in range(0, width, step):
            r, g, b = color(x, y)
            if max(abs(r-background[0]), abs(g-background[1]),
                   abs(b-background[2])) < 56:
                continue
            xmin, ymin = min(xmin, x), min(ymin, y)
            xmax, ymax = max(xmax, x), max(ymax, y)
            count += 1
    if count < 18:
        return None
    pad_x = max(8, (xmax - xmin) // 10)
    pad_y = max(8, (ymax - ymin) // 10)
    x0, y0 = max(0, xmin-pad_x), max(0, ymin-pad_y)
    x1, y1 = min(width, xmax+pad_x+step), min(height, ymax+pad_y+step)
    # Avoid over-zooming very small isolated marks to the entire card.
    min_width, min_height = int(width * .35), int(height * .35)
    if x1-x0 < min_width:
        middle = (x0+x1)//2
        x0 = max(0, middle-min_width//2)
        x1 = min(width, x0+min_width)
    if y1-y0 < min_height:
        middle = (y0+y1)//2
        y0 = max(0, middle-min_height//2)
        y1 = min(height, y0+min_height)
    if (x1-x0)*(y1-y0) > .86*width*height:
        return None
    return x0, y0, x1-x0, y1-y0


def _thumbnail_preview(filename):
    """Decode a bounded preview, crop empty margins, scale once for the card."""
    source = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(filename), 1280, 850, True)
    bounds = _content_bounds_rgb(source.get_pixels(), source.get_width(),
                                 source.get_height(), source.get_rowstride(),
                                 source.get_n_channels())
    if bounds is not None:
        source = GdkPixbuf.Pixbuf.new_subpixbuf(source, *bounds)
    # Render at >2x logical display size; never upscale an already small crop.
    factor = min(760/source.get_width(), 480/source.get_height(), 1.0)
    if factor >= 1.0:
        return source
    width = max(1, round(source.get_width() * factor))
    height = max(1, round(source.get_height() * factor))
    return source.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)



def _card_pixbuf(pixbuf, max_width=288, max_height=178):
    # Limit Gtk.Picture's natural width so Gtk.FlowBox can lay out 3 columns.
    # set_size_request() only sets a minimum, not the natural image width.
    width, height = pixbuf.get_width(), pixbuf.get_height()
    if width < 1 or height < 1:
        raise ValueError('Empty screenshot thumbnail')
    factor = min(max_width / width, max_height / height, 1.0)
    if factor >= 1.0:
        return pixbuf
    new_width = max(1, min(max_width, round(width * factor)))
    new_height = max(1, min(max_height, round(height * factor)))
    return pixbuf.scale_simple(new_width, new_height, GdkPixbuf.InterpType.HYPER)

def show_history(app, existing=None):
    if existing is not None:
        existing.present()
        return existing
    location = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
    pictures = Path(location) if location else Path.home() / 'Pictures'
    items = history_paths(pictures, Settings().screenshot_directory())
    window = Adw.ApplicationWindow(application=app, title=_('Screenshot History'),
                                    default_width=1020, default_height=680)
    view = Adw.ToolbarView()
    window.set_content(view)
    view.add_top_bar(Adw.HeaderBar())
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    view.set_content(body)
    scroll = Gtk.ScrolledWindow()
    scroll.set_vexpand(True)
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    body.append(scroll)
    if not items:
        scroll.set_child(Adw.StatusPage(icon_name='folder-pictures-symbolic',
                                      title=_('No GNOME screenshots found'),
                                      description=_('Check Screenshots & Annotation → Screenshot history folder.')))
    else:
        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_homogeneous(True)
        flow.set_max_children_per_line(3)
        flow.set_min_children_per_line(1)
        flow.set_row_spacing(12)
        flow.set_column_spacing(12)
        flow.set_margin_top(14)
        flow.set_margin_bottom(14)
        flow.set_margin_start(14)
        flow.set_margin_end(14)
        scroll.set_child(flow)
        pending = []
        position = [0]
        closed = [False]
        scheduled = [False]

        def fill_thumbnail():
            if closed[0]:
                scheduled[0] = False
                pending.clear()
                return False
            if not pending:
                scheduled[0] = False
                return False
            filename, picture = pending.pop(0)
            try:
                picture.set_paintable(Gdk.Texture.new_for_pixbuf(_card_pixbuf(_thumbnail_preview(filename))))
            except (OSError, GLib.Error, ValueError) as exc:
                print('SnapMark: history preview unavailable:', filename, str(exc), flush=True)
            scheduled[0] = bool(pending)
            return scheduled[0]

        def load_more(_button=None):
            start = position[0]
            end = min(start + 18, len(items))
            for path in items[start:end]:
                picture = Gtk.Picture()
                picture.set_content_fit(Gtk.ContentFit.CONTAIN)
                picture.set_can_shrink(True)
                picture.set_size_request(288, 178)
                picture.set_halign(Gtk.Align.CENTER)
                btn = Gtk.Button()
                btn.add_css_class('flat')
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
                box.append(picture)
                label = Gtk.Label(label=path.name)
                label.set_width_chars(23)
                label.set_max_width_chars(23)
                label.set_ellipsize(Pango.EllipsizeMode.END)
                label.add_css_class('caption')
                box.append(label)
                btn.set_child(box)
                btn.set_tooltip_text(str(path))
                btn.connect('clicked', lambda _button, p=path: app.show_editor(p))
                flow.insert(btn, -1)
                pending.append((path, picture))
            position[0] = end
            more.set_visible(end < len(items))
            if pending and not scheduled[0]:
                scheduled[0] = True
                GLib.idle_add(fill_thumbnail, priority=GLib.PRIORITY_DEFAULT_IDLE)

        more = Gtk.Button(label='Load more screenshots')
        more.set_label(_('Load more screenshots'))
        more.add_css_class('flat')
        more.set_halign(Gtk.Align.CENTER)
        more.set_margin_bottom(10)
        more.connect('clicked', load_more)
        body.append(more)
        def on_close(_window):
            closed[0] = True
            pending.clear()
            return False
        window.connect('close-request', on_close)
        # Present before image decoding; only 18 previews are queued at a time.
        window.present()
        GLib.idle_add(load_more, priority=GLib.PRIORITY_DEFAULT_IDLE)
        return window
    window.present()
    return window
