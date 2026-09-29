"""History selection and record-only commands backed by the existing records."""
from PySide6.QtCore import QObject, Property, QUrl, Qt, Signal, Slot

from yt_downloader.core.formatting import format_bytes
from yt_downloader.core.models import TASK_STATUS_MESSAGE_IDS, TaskStatus
from yt_downloader.ui.quick_state import RowModel, ViewState

TERMINAL = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}


class HistoryPresenter(ViewState):
    open_file_requested = Signal(str)
    open_folder_requested = Signal(str)
    copy_link_requested = Signal(str)
    thumbnail_requested = Signal(object)
    retry_requested = Signal(object)
    delete_requested = Signal(object)
    delete_many_requested = Signal(object)
    clear_terminal_requested = Signal()

    def __init__(self, dialogs, parent=None, translator=None):
        super().__init__(parent, managing=False, selectedId='', selectedIndex=-1,
                         fileExists=False, canDelete=False, checkedCount=0, selectableCount=0,
                         selectAllState=Qt.CheckState.Unchecked.value, managementText='')
        self.dialogs = dialogs
        self._translator = translator
        self.records = []
        self._checked = set()
        self._model = RowModel(self)
        self._images = None
        self._thumbnail_sources = {}
        self._management_result = None

    @Property(QObject, constant=True)
    def model(self):
        return self._model

    def configure_thumbnails(self, ffmpeg, directory):
        from yt_downloader.ui.quick_history_images import HistoryImageCache
        self._images = HistoryImageCache(ffmpeg, directory, self)
        self._images.ready.connect(self._thumbnail_ready)

    @Slot(str)
    def requestThumbnail(self, task_id):
        record = next((r for r in self.records if r.task_id == task_id), None)
        if self._images and record and record.status is TaskStatus.COMPLETED and record.media_mode != 'audio_only':
            self._images.request(task_id, record.file_path)

    def invalidate_thumbnail(self, task_id):
        self._thumbnail_sources.pop(task_id, None)
        if self._images:
            self._images.invalidate(task_id)
        self._refresh()
        self.requestThumbnail(task_id)

    def _thumbnail_ready(self, task_id, key, source):
        from yt_downloader.ui.quick_history_images import media_key
        record = next((r for r in self.records if r.task_id == task_id), None)
        if not record or record.status is not TaskStatus.COMPLETED:
            return
        try:
            if media_key(record.file_path) != key:
                self.requestThumbnail(task_id)
                return
        except OSError:
            return
        self._thumbnail_sources[task_id] = source
        for row in self._model.rows:
            if row['id'] == task_id:
                self._model.put(dict(row, thumbnail=source))
                break

    def close(self):
        if self._images:
            self._images.close()

    def set_records(self, records):
        self.records = records
        valid = {r.task_id for r in records}
        self._thumbnail_sources = {k: v for k, v in self._thumbnail_sources.items() if k in valid}
        self._checked.intersection_update(r.task_id for r in records if r.status in TERMINAL)
        self._refresh()
        self.select(self._state['selectedId'])

    def refresh_localized(self, *_):
        self._refresh()
        if self._management_result is not None:
            self._set_management_result(*self._management_result)

    def _refresh(self):
        selectable_count = sum(r.status in TERMINAL for r in self.records)
        checked_count = len(self._checked)
        select_all_state = (
            Qt.CheckState.Unchecked.value if checked_count == 0 else
            Qt.CheckState.Checked.value if checked_count == selectable_count else
            Qt.CheckState.PartiallyChecked.value
        )
        self._model.replace([dict(id=r.task_id, title=r.title,
                                 subtitle=f'{r.quality_label}  ·  {format_bytes(r.file_size)}',
                                 statusKey=TASK_STATUS_MESSAGE_IDS[r.status], statusCode=r.status.value, date=r.created_at,
                                 thumbnail=self._thumbnail_sources.get(r.task_id) or (QUrl.fromLocalFile(str(r.thumbnail_path)).toString() if r.thumbnail_path and r.thumbnail_path.is_file() else ''),
                                 checked=r.task_id in self._checked, deletable=r.status in TERMINAL)
                             for r in self.records])
        self.update(checkedCount=checked_count, selectableCount=selectable_count,
                    selectAllState=select_all_state,
                    managementText=(self._translator.text('history.selected_count', {'count': checked_count})
                                    if self._translator else f'已选择 {checked_count} 项'))

    def selected_record(self):
        return next((r for r in self.records if r.task_id == self._state['selectedId']), None)

    @Slot(str)
    def select(self, task_id):
        record = next((r for r in self.records if r.task_id == task_id), None)
        self.update(selectedId=record.task_id if record else '',
                    selectedIndex=self.records.index(record) if record else -1,
                    fileExists=bool(record and record.file_path.is_file()),
                    canDelete=bool(record and record.status in TERMINAL))

    @Slot(str)
    def prepareContext(self, task_id):
        """Focus the context target and align management selection with it."""
        record = next((r for r in self.records if r.task_id == task_id), None)
        if not record:
            return
        if self._state['managing']:
            if record.status in TERMINAL:
                if task_id not in self._checked:
                    self._checked = {task_id}
                    self._refresh()
            else:
                self._checked.clear()
                self._refresh()
        self.select(task_id)

    @Slot(bool)
    def manage(self, enabled):
        if not enabled:
            self._checked.clear()
        self.update(managing=enabled)
        self._refresh()

    @Slot(str)
    def toggle(self, task_id):
        if not self._state['managing'] or not any(r.task_id == task_id and r.status in TERMINAL for r in self.records):
            return
        if task_id in self._checked:
            self._checked.remove(task_id)
        else:
            self._checked.add(task_id)
        self._refresh()

    @Slot(bool)
    def selectAll(self, checked):
        if self._state['managing']:
            self._checked = {r.task_id for r in self.records if r.status in TERMINAL} if checked else set()
            self._refresh()

    @Slot(str)
    def action(self, action):
        record = self.selected_record()
        if not record:
            return
        if action in {'open', 'folder', 'cover'} and not record.file_path.is_file():
            self.select(record.task_id)
            return
        if action == 'open':
            self.open_file_requested.emit(str(record.file_path))
        elif action == 'folder':
            self.open_folder_requested.emit(str(record.file_path))
        elif action == 'copy':
            self.copy_link_requested.emit(record.url)
        elif action == 'retry':
            self.retry_requested.emit(record)
        elif action == 'cover':
            self.thumbnail_requested.emit(record)
        elif action == 'delete' and record.status in TERMINAL:
            if self._state['managing'] and record.task_id in self._checked:
                self.deleteChecked()
                return
            title = self._translator.text('history.delete_dialog_title') if self._translator else '删除历史记录'
            body = (self._translator.text('history.delete_record_body', {'title': record.title})
                    if self._translator else f'确定删除“{record.title}”的历史记录吗？\n只删除记录，已经下载的视频文件会保留。')
            button = self._translator.text('history.delete_record_button') if self._translator else '删除记录'
            self.dialogs.confirm(title, body, button,
                                 lambda accepted: self.delete_requested.emit(record) if accepted else None)

    @Slot()
    def deleteChecked(self):
        ids = tuple(r.task_id for r in self.records if r.task_id in self._checked)
        if ids:
            title = (self._translator.text('history.delete_selected_dialog_title')
                     if self._translator else '删除所选历史记录')
            body = (self._translator.text('history.delete_selected_dialog_body', {'count': len(ids)})
                    if self._translator else f'确定删除所选的 {len(ids)} 条历史记录吗？\n只删除终态记录，不删除视频文件。')
            button = self._translator.text('history.delete_button') if self._translator else '删除'
            self.dialogs.confirm(title, body, button,
                                 lambda accepted: self.delete_many_requested.emit(ids) if accepted else None)

    @Slot()
    def clearTerminal(self):
        self.dialogs.confirm('清空历史记录', '确定清空所有可删除的历史记录吗？\n活动与排队记录会保留，已经下载的视频文件不会删除。',
                             '删除', lambda accepted: self.clear_terminal_requested.emit() if accepted else None)

    def show_management_result(self, deleted_count, retained_count):
        self._management_result = (deleted_count, retained_count)
        self._set_management_result(deleted_count, retained_count)

    def _set_management_result(self, deleted_count, retained_count):
        if self._translator:
            key = 'history.management_result' if retained_count else 'history.deleted_count'
            params = {'deleted': deleted_count, 'retained': retained_count} if retained_count else {'deleted': deleted_count}
            message = self._translator.text(key, params)
        else:
            message = f'已删除 {deleted_count} 项；保留 {retained_count} 项不可删除记录' if retained_count else f'已删除 {deleted_count} 项'
        self.update(managementText=message)

    def batch_delete_succeeded(self, deleted_count, retained_count):
        """Leave selection mode only after the repository confirms deletion."""
        self.show_management_result(deleted_count, retained_count)
        self.manage(False)
