import queue as queue_mod


def test_with_depth():
    from voxd.core.voxd_core import _with_depth
    assert _with_depth("Recording", 0) == "Recording"
    assert _with_depth("Recording", 2) == "Recording (+2 queued)"
    assert _with_depth("Transcribing", 1) == "Transcribing (+1 queued)"
    assert _with_depth("Typing", 0) == "Typing"


def test_worker_processes_fifo_in_order(monkeypatch):
    from voxd.core import voxd_core as vc

    calls = []

    def fake_process(cfg, logger, path, rec_start, rec_end, on_status=None):
        calls.append(path)
        return f"text-for-{path}"

    monkeypatch.setattr(vc, "_process_audio_file", fake_process)

    jobs = queue_mod.Queue()
    for name in ("a.wav", "b.wav", "c.wav"):
        jobs.put({"path": name, "rec_start": None, "rec_end": None})

    statuses, items, drained = [], [], []
    worker = vc.QueueWorkerThread(cfg=None, logger=None, jobs=jobs)
    worker.status_changed.connect(statuses.append)
    worker.item_finished.connect(items.append)
    worker.drained.connect(lambda: drained.append(True))
    worker.run()  # synchronous: no threads needed

    assert calls == ["a.wav", "b.wav", "c.wav"]
    assert items == ["text-for-a.wav", "text-for-b.wav", "text-for-c.wav"]
    assert drained == [True]
    assert any(s.startswith("Transcribing") for s in statuses)


def test_stage_job_unique_names(tmp_path):
    from voxd.core.voxd_core import DictationQueue

    q = DictationQueue(cfg=None, logger=None)
    first = tmp_path / "last_recording.wav"
    first.write_bytes(b"one")
    staged_first = q._stage_job(str(first))
    second = tmp_path / "last_recording.wav"
    second.write_bytes(b"two")
    staged_second = q._stage_job(str(second))
    assert staged_first != staged_second
    assert staged_first.endswith(".wav") and staged_second.endswith(".wav")


def test_controller_enqueues_and_drains(monkeypatch):
    from PyQt6.QtCore import QObject, pyqtSignal
    from voxd.core import voxd_core as vc

    class FakeWorker(QObject):
        status_changed = pyqtSignal(str)
        item_finished = pyqtSignal(str)
        drained = pyqtSignal()

        def __init__(self, cfg, logger, jobs):
            super().__init__()
            self.jobs = jobs

        def start(self):
            while not self.jobs.empty():
                job = self.jobs.get_nowait()
                self.status_changed.emit("Transcribing")
                self.item_finished.emit(f"done-{job['path']}")
            self.drained.emit()

    monkeypatch.setattr(vc, "QueueWorkerThread", FakeWorker)

    statuses, items, drained = [], [], []
    q = vc.DictationQueue(cfg=None, logger=None)
    q.status_changed.connect(statuses.append)
    q.item_finished.connect(items.append)
    q.queue_drained.connect(lambda: drained.append(True))

    q._on_recorded({"path": "/tmp/fake1.wav", "rec_start": None, "rec_end": None})
    assert q.jobs.qsize() == 0  # consumed by the fake worker
    assert items == ["done-/tmp/fake1.wav"]
    # The synchronous fake drains inline, so drained may fire twice;
    # with real async threads it fires exactly once per drain.
    assert len(drained) >= 1
