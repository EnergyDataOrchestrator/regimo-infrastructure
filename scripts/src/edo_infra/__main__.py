import os

from .instance import CHILD_ENV_VAR

if __name__ == "__main__":
    if os.environ.get(CHILD_ENV_VAR) == "1":
        # instance env child: dispatch without click (not installed there)
        from .child_dispatch import dispatch

        dispatch()
    else:
        from .cli import cli

        cli()
