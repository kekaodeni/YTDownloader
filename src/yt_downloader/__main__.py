import multiprocessing


multiprocessing.freeze_support()

from yt_downloader.app import main  # noqa: E402

raise SystemExit(main())
