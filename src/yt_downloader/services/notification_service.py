"""Task lifecycle notifications, with one summary per Collection batch."""
from collections import OrderedDict


def is_app_foreground(window, application):
    """Only a visible, active, non-minimized application owns foreground UI."""
    from PySide6.QtCore import Qt
    return (window.isVisible() and window.isActive()
            and not (window.windowState() & Qt.WindowMinimized)
            and application.applicationState() == Qt.ApplicationActive)


class NotificationCoordinator:
    def __init__(self, translator, sink, *, is_foreground, enabled, inline):
        self.translator, self.sink = translator, sink
        self.is_foreground, self.enabled, self.inline = is_foreground, enabled, inline
        self._batches = {}
        self._finished = OrderedDict()

    def register_batch(self, requests):
        for request in requests:
            if request.batch_id:
                self._batches.setdefault(request.batch_id, {})[request.task_id] = None

    def queued(self, request):
        """A user retry starts a new attempt; duplicate terminal signals do not."""
        self._finished.pop(request.task_id, None)
        batch = self._batches.get(request.batch_id)
        if batch is not None:
            batch[request.task_id] = None

    def finished(self, request, outcome):
        if not request or outcome not in {'completed', 'failed', 'cancelled'} or request.task_id in self._finished:
            return
        self._finished[request.task_id] = None
        if len(self._finished) > 10000:
            self._finished.popitem(last=False)
        batch = self._batches.get(request.batch_id)
        if batch is not None:
            batch[request.task_id] = outcome
            if any(value is None for value in batch.values()):
                return
            self._batches.pop(request.batch_id)
            counts = {key: list(batch.values()).count(key) for key in ('completed', 'failed', 'cancelled')}
            key = 'notification.batch_cancelled' if counts['cancelled'] else 'notification.batch_summary' if counts['failed'] else 'notification.batch_success'
            self.notify('notification.batch_complete', self.translator.text(key, counts))
        elif outcome != 'cancelled':
            self.notify('notification.complete' if outcome == 'completed' else 'notification.failed', request.video.title)

    def notify(self, title_key, body):
        if not self.enabled() or self.is_foreground():
            return
        title = self.translator.text(title_key)
        self.sink.send(title, body)
