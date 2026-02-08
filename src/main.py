import argparse
import getpass
import json
import os
import sys
from typing import Dict, List, Optional

from ticketforge_client import DEFAULT_BASE_URL, TicketForgeClient, TicketForgeConfig


CONFIG_FILE = "config.json"


def load_config() -> TicketForgeConfig:
    if not os.path.exists(CONFIG_FILE):
        raise RuntimeError("Config not found. Run: python main.py setup")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return TicketForgeConfig(
        base_url=data["base_url"],
        username=data["username"],
        password=data["password"],
    )


def save_config(base_url: str, username: str, password: str) -> None:
    data = {"base_url": base_url, "username": username, "password": password}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def parse_csv_refs(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return parts if parts else None


def parse_custom_fields(value: Optional[str]) -> Optional[Dict[str, str]]:
    if not value:
        return None
    out: Dict[str, str] = {}
    for pair in value.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise RuntimeError("Invalid custom fields format. Use: key=value,key2=value2")
        k, v = pair.split("=", 1)
        out[k.strip()] = v.strip()
    return out if out else None


def print_table(workitems: List[dict]) -> None:
    if not workitems:
        print("No tickets found.")
        return

    headers = ["REF", "TITLE", "STAGE", "UPDATED"]
    rows = []
    for w in workitems:
        rows.append([w.get("ref", ""), w.get("title", ""), w.get("stage", ""), w.get("updated", "")])

    widths = [len(h) for h in headers]
    for r in rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(str(cell)))

    def fmt_row(cols: List[str]) -> str:
        return "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(cols))

    print(fmt_row(headers))
    print(fmt_row(["-" * w for w in widths]))
    for r in rows:
        print(fmt_row([str(c) for c in r]))


def cmd_setup(args: argparse.Namespace) -> None:
    base_url = args.base_url or DEFAULT_BASE_URL
    username = args.username or input("Username: ").strip()
    password = args.password or getpass.getpass("Password: ")

    cfg = TicketForgeConfig(base_url=base_url, username=username, password=password)
    client = TicketForgeClient(cfg)
    client.health_check()

    save_config(base_url, username, password)
    print("Setup complete. Connection verified.")


def cmd_list(args: argparse.Namespace) -> None:
    cfg = load_config()
    client = TicketForgeClient(cfg)

    if args.all:
        items = client.list_all_workitems(batch_size=args.limit)
        print_table(items)
        print(f"\nTotal: {len(items)} tickets")
        return

    items, pagination = client.list_workitems(limit=args.limit)
    print_table(items)
    has_more = pagination.get("hasMore")
    if has_more:
        print("")
        print("More results available. Try: python src/main.py list --all")


def cmd_show(args: argparse.Namespace) -> None:
    cfg = load_config()
    client = TicketForgeClient(cfg)

    ref = args.ref
    w = client.get_workitem_deep(ref)

    print(f"REF: {w.get('ref', '')}")
    print(f"TITLE: {w.get('title', '')}")
    print(f"STAGE: {w.get('stage', '')}")
    print(f"UPDATED: {w.get('updated', '')}")
    print(f"CREATED: {w.get('created', '')}")

    depends = w.get("dependsOn") or []
    if depends:
        print(f"DEPENDS_ON: {', '.join(depends)}")

    owner = w.get("owner") or {}
    if owner.get("username"):
        print(f"OWNER: {owner.get('username')}")

    desc = w.get("description")
    if desc is not None:
        print("")
        print("DESCRIPTION:")
        print(desc)


def cmd_create(args: argparse.Namespace) -> None:
    cfg = load_config()
    client = TicketForgeClient(cfg)

    title = args.title or input("Title: ").strip()
    description = args.description or input("Description: ").strip()
    depends_on = parse_csv_refs(args.depends_on)

    workitem = client.create_workitem(title=title, description=description, depends_on=depends_on)
    print(f"Created {workitem.get('ref', '')}: {workitem.get('title', '')}")


def cmd_update(args: argparse.Namespace) -> None:
    cfg = load_config()
    client = TicketForgeClient(cfg)

    ref = args.ref
    depends_on = parse_csv_refs(args.depends_on)
    custom_fields = parse_custom_fields(args.custom_fields)

    client.update_workitem(
        ref=ref,
        title=args.title,
        description=args.description,
        stage=args.stage,
        depends_on=depends_on,
        custom_fields=custom_fields,
    )
    print(f"Updated {ref}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ticketforge-cli", description="TicketForge CLI integration")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("setup", help="Configure connection to TicketForge")
    s.add_argument("--base-url", default=DEFAULT_BASE_URL)
    s.add_argument("--username")
    s.add_argument("--password")
    s.set_defaults(func=cmd_setup)

    l = sub.add_parser("list", help="List your tickets")
    l.add_argument("--limit", type=int, default=5)
    l.add_argument("--all", action="store_true")
    l.set_defaults(func=cmd_list)

    sh = sub.add_parser("show", help="Show a ticket in detail")
    sh.add_argument("ref", help="Ticket ref, e.g. TF-160")
    sh.set_defaults(func=cmd_show)

    c = sub.add_parser("create", help="Create a new ticket")
    c.add_argument("--title")
    c.add_argument("--description")
    c.add_argument("--depends-on", help="Comma-separated ticket refs, e.g. TF-157,TF-158")
    c.set_defaults(func=cmd_create)

    u = sub.add_parser("update", help="Update an existing ticket")
    u.add_argument("ref", help="Ticket ref, e.g. TF-160")
    u.add_argument("--title")
    u.add_argument("--description")
    u.add_argument("--stage", help="open | in_progress | review | closed")
    u.add_argument("--depends-on", help="Comma-separated ticket refs")
    u.add_argument("--custom-fields", help="Comma-separated key=value pairs, e.g. j9=eee,k2=val")
    u.set_defaults(func=cmd_update)

    return p


def main() -> None:
    try:
        parser = build_parser()
        args = parser.parse_args()
        args.func(args)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
