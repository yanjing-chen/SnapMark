"""Integrated GTK4 OCR panel for SnapMark, not an installable plugin."""
from __future__ import annotations

import threading
import time
from pathlib import Path

from gi.repository import Adw, Gdk, GLib, Gtk, Pango

from .ocr_ollama import (DEFAULT_MODEL, OllamaOCR, OllamaError,
                         load_ocr_settings, save_ocr_settings)
from .preferences import Settings


def tr(zh: str, en: str) -> str:
    return zh if Settings().language() == "zh_CN" else en


class OCRPanel(Gtk.Box):
    """OCR extracts original pixels and keeps annotation layers untouched."""

    def __init__(self, editor):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.editor = editor
        self._cancel_event = threading.Event()
        self._running = False
        self._follow = True
        self.set_margin_start(8)
        self.set_margin_end(8)
        self.set_margin_top(7)
        self.set_margin_bottom(7)
        self.set_size_request(-1, 170)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        self.append(bar)
        title = Gtk.Label(label="OCR · Ollama", xalign=0)
        title.add_css_class("heading")
        title.set_hexpand(True)
        bar.append(title)
        self.run_button = Gtk.Button(label=tr("识别当前截图", "Recognize screenshot"))
        self.run_button.add_css_class("suggested-action")
        self.run_button.connect("clicked", lambda *_: self.run())
        bar.append(self.run_button)
        self.region_button = Gtk.Button(label=tr("选取区域", "Select region"))
        self.region_button.connect("clicked", self._select_region)
        bar.append(self.region_button)
        self.cancel_button = Gtk.Button(label=tr("取消", "Cancel"))
        self.cancel_button.set_sensitive(False)
        self.cancel_button.connect("clicked", self._cancel)
        bar.append(self.cancel_button)

        scroll = Gtk.ScrolledWindow()
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        scroll.set_min_content_height(115)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.append(scroll)
        self.view = Gtk.TextView()
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_left_margin(10)
        self.view.set_right_margin(10)
        self.view.set_top_margin(7)
        self.view.set_bottom_margin(7)
        self.view.get_buffer().set_text("")
        self.view.get_buffer().set_enable_undo(True)
        scroll.set_child(self.view)
        self.scroll = scroll
        scroll.get_vadjustment().connect("value-changed", self._on_scroll)

        foot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        self.append(foot)
        self.status = Gtk.Label(label=tr("就绪", "Ready"), xalign=0)
        self.status.set_hexpand(True)
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        foot.append(self.status)
        copy = Gtk.Button(label=tr("复制文字", "Copy text"))
        copy.connect("clicked", self._copy)
        foot.append(copy)
        save = Gtk.Button(label=tr("保存 TXT", "Save TXT"))
        save.connect("clicked", self._save)
        foot.append(save)
        clear = Gtk.Button(label=tr("清空", "Clear"))
        clear.connect("clicked", self._clear)
        foot.append(clear)

    def _on_scroll(self, adjustment):
        bottom = adjustment.get_upper() - adjustment.get_page_size()
        self._follow = bottom <= 0 or adjustment.get_value() >= bottom - 20

    def _status(self, message):
        self.status.set_text(str(message))
        return GLib.SOURCE_REMOVE

    def _begin(self):
        self._running = True
        self._cancel_event.clear()
        self.run_button.set_sensitive(False)
        self.region_button.set_sensitive(False)
        self.cancel_button.set_sensitive(True)
        self.view.set_editable(False)
        self._follow = True
        self.view.get_buffer().set_text("")
        self._status(tr("正在识别……", "Recognizing…"))

    def _end(self, state):
        self._running = False
        self.run_button.set_sensitive(True)
        self.region_button.set_sensitive(True)
        self.cancel_button.set_sensitive(False)
        self.view.set_editable(True)
        self._status(state)
        return GLib.SOURCE_REMOVE

    def _insert(self, value):
        if self._cancel_event.is_set():
            return GLib.SOURCE_REMOVE
        buffer = self.view.get_buffer()
        end = buffer.get_end_iter()
        buffer.insert(end, value)
        if self._follow:
            mark = buffer.create_mark(None, buffer.get_end_iter(), False)
            self.view.scroll_to_mark(mark, 0, False, 0.0, 0.0)
            buffer.delete_mark(mark)
        return GLib.SOURCE_REMOVE

    def run(self, png=None):
        if self._running:
            return
        if png is None:
            try:
                png = self.editor.original_png_for_ocr()
            except Exception as exc:
                self._status(str(exc))
                return
        self._begin()
        cancel = self._cancel_event

        def worker():
            started = time.monotonic()
            try:
                client = OllamaOCR()
                if not client.is_installed():
                    raise OllamaError(tr("所选 OCR 模型未安装；请在首选项 → OCR 选择或安装模型", "Selected OCR model is not installed; open Preferences → OCR"))
                for chunk in client.recognize(png, cancelled=cancel.is_set):
                    if cancel.is_set():
                        break
                    GLib.idle_add(self._insert, chunk)
                if cancel.is_set():
                    state = tr("已取消", "Cancelled")
                else:
                    state = tr("识别完成", "Completed") + f" · {time.monotonic()-started:.1f}s"
            except Exception as exc:
                state = f"OCR: {exc}"
            GLib.idle_add(self._end, state)

        threading.Thread(target=worker, name="snapmark-ollama-ocr", daemon=True).start()

    def _select_region(self, *_args):
        # The callback is invoked by editor.py's existing pixel-space selection.
        self.editor.request_ocr_region(self.run)

    def _cancel(self, *_args):
        if self._running:
            self._cancel_event.set()
            self._status(tr("正在取消……", "Cancelling…"))

    def _get_text(self):
        buffer = self.view.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)

    def _copy(self, *_args):
        text = self._get_text()
        if text:
            self.get_display().get_clipboard().set(text)
            self._status(tr("已复制到剪贴板", "Copied to clipboard"))

    def _clear(self, *_args):
        if not self._running:
            self.view.get_buffer().set_text("")
            self._status(tr("已清空", "Cleared"))

    def _save(self, *_args):
        text = self._get_text()
        if not text:
            return
        dialog = Gtk.FileDialog(title=tr("保存 OCR 文字", "Save OCR text"))
        dialog.set_initial_name("SnapMark-OCR.txt")
        def saved(dlg, result):
            try:
                chosen = dlg.save_finish(result)
                if chosen and chosen.get_path():
                    Path(chosen.get_path()).write_text(text, encoding="utf-8")
                    self._status(tr("文字已保存", "Text saved"))
            except GLib.Error as exc:
                if "cancel" not in str(exc).lower() and "dismiss" not in str(exc).lower():
                    self._status(str(exc))
            except OSError as exc:
                self._status(str(exc))
        dialog.save(self.editor, None, saved)


def create_ocr_preferences(editor):
    """Native OCR preferences. All model choices remain local to SnapMark."""
    from .ocr_ollama import (detect_model_folder, validate_model_name,
                             validate_hidden_models)

    page = Adw.PreferencesPage()
    cfg = load_ocr_settings()
    state = {'models': [], 'candidate': '', 'refreshing': False, 'busy': False,
             'folder': '', 'folder_info': None}

    def notice(msg):
        model_status.set_subtitle(str(msg))
        return GLib.SOURCE_REMOVE

    def dialog_box(heading, body, buttons=('ok',), on_response=None, extra=None):
        dlg = Adw.MessageDialog.new(editor, heading, body)
        if extra is not None:
            dlg.set_extra_child(extra)
        if 'cancel' in buttons:
            dlg.add_response('cancel', tr('取消', 'Cancel'))
            dlg.set_close_response('cancel')
            dlg.set_default_response('cancel')
        if 'delete' in buttons:
            dlg.add_response('delete', tr('删除', 'Delete'))
            dlg.set_response_appearance('delete', Adw.ResponseAppearance.DESTRUCTIVE)
        if 'ok' in buttons:
            dlg.add_response('ok', tr('确定', 'OK'))
        if on_response is not None:
            dlg.connect('response', on_response)
        dlg.present()
        return dlg

    def job(button, operation, done=None):
        button.set_sensitive(False)
        def worker():
            try:
                result = operation(OllamaOCR())
            except Exception as exc:
                GLib.idle_add(notice, str(exc))
                def show_failure(message):
                    dialog_box(tr('操作未完成', 'Operation failed'), message)
                    return GLib.SOURCE_REMOVE
                GLib.idle_add(show_failure, str(exc))
            else:
                if done:
                    GLib.idle_add(done, result)
            finally:
                GLib.idle_add(button.set_sensitive, True)
        threading.Thread(target=worker, name='snapmark-ollama-ocr-settings', daemon=True).start()

    # Part 1: Local Ollama status; service installation belongs to the OS.
    group = Adw.PreferencesGroup(
        title=tr('OCR · Ollama', 'OCR · Ollama'),
        description=tr('识别使用本机 Ollama；不会修改 Popup 等其他应用的模型设置。',
                       'Uses local Ollama without changing other apps’ preferences.'))
    page.add(group)
    group.add(Adw.ActionRow(title='Ollama', subtitle='http://127.0.0.1:11434'))

    model_status = Adw.ActionRow(title=tr('模型状态', 'Model status'),
                                 subtitle=tr('正在检查 Ollama……', 'Checking Ollama…'))
    group.add(model_status)
    seconds_row = Adw.ActionRow(
        title=tr('模型自动退出显存时间', 'Model GPU memory retention'),
        subtitle=tr('单位：秒。0 表示 OCR 完成后请求立即卸载。',
                    'Seconds. 0 requests immediate unload after OCR.'))
    adj = Gtk.Adjustment(value=cfg['keep_alive_seconds'], lower=0, upper=86400,
                         step_increment=1, page_increment=60, page_size=0)
    spin = Gtk.SpinButton(adjustment=adj, climb_rate=1, digits=0)
    spin.set_numeric(True)
    spin.set_width_chars(7)
    spin.set_valign(Gtk.Align.CENTER)
    seconds_row.add_suffix(spin)
    group.add(seconds_row)
    def seconds_changed(_widget):
        try:
            save_ocr_settings(keep_alive_seconds=int(spin.get_value()))
        except Exception as exc:
            notice(exc)
    spin.connect('value-changed', seconds_changed)

    # Part 2: Installed list, active selection, download in the exact requested order.
    models_group = Adw.PreferencesGroup(title=tr('OCR 模型', 'OCR models'))
    page.add(models_group)
    installed = Adw.ActionRow(title=tr('已安装的 OCR 模型', 'Installed OCR models'))
    model_menu = Gtk.MenuButton()
    model_menu.set_valign(Gtk.Align.CENTER)
    menu_label = Gtk.Label(label=tr('请选择', 'Select model'), xalign=0)
    menu_label.set_single_line_mode(True)
    menu_label.set_ellipsize(Pango.EllipsizeMode.END)
    menu_label.set_width_chars(16)
    menu_label.set_max_width_chars(24)
    model_menu.set_child(menu_label)
    model_menu.set_tooltip_text(tr('选择用于 OCR 的模型', 'Choose an OCR model'))
    pop = Gtk.Popover()
    scroll = Gtk.ScrolledWindow()
    scroll.set_min_content_width(320)
    scroll.set_max_content_height(270)
    scroll.set_propagate_natural_height(True)
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    choices = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    choices.set_margin_start(4); choices.set_margin_end(4)
    choices.set_margin_top(3); choices.set_margin_bottom(3)
    scroll.set_child(choices)
    pop.set_child(scroll)
    model_menu.set_popover(pop)
    installed.add_suffix(model_menu)
    refresh = Gtk.Button(label=tr('刷新列表', 'Refresh'))
    refresh.set_valign(Gtk.Align.CENTER)
    installed.add_suffix(refresh)
    enable = Gtk.Button(label=tr('启用', 'Enable'))
    enable.set_valign(Gtk.Align.CENTER)
    enable.set_sensitive(False)
    installed.add_suffix(enable)
    models_group.add(installed)

    active_row = Adw.ActionRow(title=tr('当前识别模型', 'Active OCR model'),
             subtitle=cfg['model'] or tr('尚未启用', 'Not enabled'))
    models_group.add(active_row)

    download_row = Adw.ActionRow(title=tr('从 Ollama 下载模型', 'Download from Ollama'))
    download_entry = Gtk.Entry()
    download_entry.set_placeholder_text(tr('输入模型名称，如：seriouswebby/paddleocr-vl-1.6:spotting',
                                           'Ollama model tag'))
    download_entry.set_width_chars(28)
    download_entry.set_valign(Gtk.Align.CENTER)
    download_row.add_suffix(download_entry)
    download_btn = Gtk.Button(label=tr('下载 / 更新', 'Download / update'))
    download_btn.set_valign(Gtk.Align.CENTER)
    download_row.add_suffix(download_btn)
    models_group.add(download_row)

    def activate(_button):
        name = state['candidate']
        if not name or name not in state['models']:
            notice(tr('请先选择已安装的 OCR 模型', 'Select an installed OCR model'))
            return
        try:
            save_ocr_settings(model=name)
        except Exception as exc:
            notice(exc)
        else:
            active_row.set_subtitle(name)
            notice(tr('已启用 OCR 模型：', 'Enabled OCR model: ') + name)
    enable.connect('clicked', activate)

    def model_button_text(value):
        menu_label.set_text(value)
        model_menu.set_tooltip_text(value)

    def append_only_model(name):
        """Import/download adds one model; only Refresh rescans the entire Ollama library."""
        rebuild_choices(sorted(set(state['models']) | {name}, key=str.casefold))

    def rebuild_choices(names):
        while child := choices.get_first_child():
            choices.remove(child)
        state['models'] = list(names)
        if state['candidate'] not in names:
            state['candidate'] = ''
            model_button_text(tr('请选择', 'Select model'))
            enable.set_sensitive(False)
        else:
            model_button_text(state['candidate'])
            enable.set_sensitive(True)
        if not names:
            choices.append(Gtk.Label(label=tr('未发现已添加的 OCR 模型', 'No OCR models in the list')))
        for name in names:
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            choose = Gtk.Button()
            choice_label = Gtk.Label(label=name, xalign=0)
            choice_label.set_single_line_mode(True)
            choice_label.set_ellipsize(Pango.EllipsizeMode.END)
            choice_label.set_width_chars(24)
            choice_label.set_max_width_chars(36)
            choose.set_child(choice_label)
            choose.set_tooltip_text(name)
            choose.add_css_class('flat')
            choose.set_hexpand(True)
            choose.set_halign(Gtk.Align.FILL)
            def pick(_button, picked=name):
                state['candidate'] = picked
                model_button_text(picked)
                enable.set_sensitive(True)
                pop.popdown()
            choose.connect('clicked', pick)
            line.append(choose)
            minus = Gtk.Button(icon_name='list-remove-symbolic')
            minus.set_tooltip_text(tr('从 OCR 列表删除', 'Remove from OCR list'))
            minus.add_css_class('flat')
            minus.add_css_class('destructive-action')
            minus.connect('clicked', lambda _button, picked=name: confirm_delete(picked))
            line.append(minus)
            choices.append(line)
        return GLib.SOURCE_REMOVE

    def refresh_models(_button=None, *, explicitly_requested=False):
        def worker():
            try:
                cli = OllamaOCR()
                version = cli.status()
                available = cli.vision_models()
                if explicitly_requested:
                    # Only the actual "Refresh" action restores previously hidden
                    # models that STILL exist in Ollama. Deleted model files are absent.
                    save_ocr_settings(hidden_models=[])
                    names = available
                else:
                    hidden = set(load_ocr_settings()['hidden_models'])
                    names = [name for name in available if name not in hidden]
                def update():
                    rebuild_choices(names)
                    current = load_ocr_settings()['model']
                    if current and current not in available:
                        save_ocr_settings(model='')
                        active_row.set_subtitle(tr('尚未启用', 'Not enabled'))
                    notice(f'Ollama {version} · {len(names)} '
                           + tr('个 OCR 模型', 'OCR models'))
                    return GLib.SOURCE_REMOVE
                GLib.idle_add(update)
            except Exception as exc:
                GLib.idle_add(notice, str(exc))
        threading.Thread(target=worker, name='snapmark-ocr-refresh', daemon=True).start()
    refresh.connect('clicked', lambda button: refresh_models(button, explicitly_requested=True))

    def confirm_delete(name):
        pop.popdown()
        check = Gtk.CheckButton(label=tr('同时删除本地模型文件（从 Ollama 删除；不会删除原始 GGUF 文件）',
                                         'Also delete local Ollama model (original GGUF files are untouched)'))
        check.set_margin_top(8)
        def answer(_dialog, response):
            if response != 'delete':
                return
            remove_from_ollama = check.get_active()
            def operation(cli):
                if remove_from_ollama:
                    cli.delete_model(name)
                cfg_now = load_ocr_settings()
                hidden = validate_hidden_models(cfg_now['hidden_models'] + [name])
                changes = {'hidden_models': hidden}
                if cfg_now['model'] == name:
                    changes['model'] = ''
                save_ocr_settings(**changes)
                return name
            def finished(_name):
                if not load_ocr_settings()['model']:
                    active_row.set_subtitle(tr('尚未启用', 'Not enabled'))
                state['candidate'] = ''
                rebuild_choices([item for item in state['models'] if item != name])
                notice(tr('已从 OCR 列表删除：', 'Removed from OCR list: ') + name)
            job(refresh, operation, finished)
        dialog_box(tr('确认从列表删除该模型吗？', 'Remove this model from the list?'), name,
                   buttons=('cancel','delete'), on_response=answer, extra=check)

    def download(_button):
        name = download_entry.get_text().strip()
        try:
            validate_model_name(name)
        except OllamaError as exc:
            notice(exc)
            return
        def operation(cli):
            cli.pull(name, on_status=lambda msg: GLib.idle_add(notice, msg))
            cli._verify_vision(name)
            cfg_now = load_ocr_settings()
            save_ocr_settings(hidden_models=[n for n in cfg_now['hidden_models'] if n != name])
            return name
        def done(_name):
            download_entry.set_text('')
            append_only_model(name)
            notice(tr('模型下载完成，请在列表中选择并启用：', 'Downloaded. Select and enable: ') + name)
        job(download_btn, operation, done)
    download_btn.connect('clicked', download)

    # Part 3: Folder import only. The folder choice is an ephemeral operation input.
    import_group = Adw.PreferencesGroup(title=tr('导入本地 OCR 模型', 'Import local OCR model'))
    page.add(import_group)
    folder_row = Adw.ActionRow(title=tr('导入 OCR 模型文件', 'Import OCR model files'),
                 subtitle=tr('选择包含主 GGUF、可选 mmproj GGUF 或 Modelfile 的文件夹',
                             'Choose a folder with a main GGUF, optional mmproj, or Modelfile'))
    select_folder = Gtk.Button(label=tr('选择文件夹', 'Choose folder'))
    select_folder.set_valign(Gtk.Align.CENTER)
    folder_row.add_suffix(select_folder)
    import_group.add(folder_row)
    blank_hint = folder_row.get_subtitle()

    def pick_folder(_button):
        dialog = Gtk.FileDialog(title=tr('选择 OCR 模型文件夹', 'Select OCR model directory'))
        def chosen(dlg, result):
            try:
                item = dlg.select_folder_finish(result)
                if item is None or not item.get_path():
                    return
                from .ocr_ollama import detect_model_folder
                location = item.get_path()
                found = detect_model_folder(location)
                state['folder'] = location
                state['folder_info'] = found
                description = (str(found['folder']) + ' · '
                               + (tr('Modelfile', 'Modelfile') if found['mode']=='modelfile'
                                  else found['main'].name +
                                       (' + ' + found['projector'].name if found['projector'] else '')))
                folder_row.set_subtitle(description)
                notice(tr('已识别目录中的 OCR 模型文件', 'Detected OCR model files in folder'))
            except GLib.Error as exc:
                if 'cancel' not in str(exc).lower() and 'dismiss' not in str(exc).lower():
                    notice(exc)
            except Exception as exc:
                state['folder'] = ''
                state['folder_info'] = None
                folder_row.set_subtitle(blank_hint)
                notice(exc)
                dialog_box(tr('无法识别模型目录', 'Model directory not recognized'), str(exc))
        dialog.select_folder(editor, None, chosen)
    select_folder.connect('clicked', pick_folder)

    name_row = Adw.ActionRow(title=tr('导入后的 Ollama 模型名称', 'Ollama model name after import'))
    name_input = Gtk.Entry()
    name_input.set_placeholder_text(tr('输入新模型名称', 'Enter a new model name'))
    name_input.set_width_chars(30)
    name_input.set_valign(Gtk.Align.CENTER)
    name_row.add_suffix(name_input)
    import_group.add(name_row)

    import_row = Adw.ActionRow(title=tr('导入', 'Import'))
    import_button = Gtk.Button(label=tr('导入', 'Import'))
    import_button.set_valign(Gtk.Align.CENTER)
    import_row.add_suffix(import_button)
    import_group.add(import_row)

    def import_folder(_button):
        folder = state['folder']
        name = name_input.get_text().strip()
        try:
            validate_model_name(name)
            if not folder:
                raise OllamaError(tr('请先选择模型文件夹', 'Choose a model directory first'))
        except Exception as exc:
            notice(exc)
            return
        def operation(cli):
            # Raise before upload if Ollama already has the requested name.
            result = cli.import_model_folder(folder, name,
                  on_status=lambda msg: GLib.idle_add(notice, msg))
            current = load_ocr_settings()
            save_ocr_settings(hidden_models=[m for m in current['hidden_models'] if m != name])
            return result
        def success(_name):
            # These paths are one-shot inputs, never persisted in OCR settings.
            state['folder'] = ''
            state['folder_info'] = None
            folder_row.set_subtitle(blank_hint)
            name_input.set_text('')
            append_only_model(name)
            notice(tr('导入完成；请在已安装列表中选择并启用：',
                      'Import completed; select and enable: ') + name)
        job(import_button, operation, success)
    import_button.connect('clicked', import_folder)

    refresh_models()
    return page
