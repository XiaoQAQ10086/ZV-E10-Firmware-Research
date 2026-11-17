import sys

if len(sys.argv) > 1 and sys.argv[1] in {"__serve", "__sound-serve"}:
    if sys.argv[1] == "__sound-serve":
        from zve10_installer.frozen import serve_sound_upstream

        raise SystemExit(serve_sound_upstream(sys.argv[2:]))
    from zve10_installer.frozen import serve_upstream

    raise SystemExit(serve_upstream(sys.argv[2:]))

from zve10_installer.gui import main

raise SystemExit(main())
