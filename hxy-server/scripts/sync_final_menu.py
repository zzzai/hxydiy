"""Compatibility entry point for the authenticated, preview-first confirmed menu tool."""

from scripts.apply_confirmed_menu import main, plan_menu


def sync_final_menu(db, store_id, *, apply=False):
    if apply:
        raise ValueError("use the authenticated confirmed-menu CLI with preview SHA and verified backup")
    return plan_menu(db, store_id)


if __name__ == "__main__":
    main()
