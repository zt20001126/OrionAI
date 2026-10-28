"""只读比较 orionai 与 checkpoint 中的 Checkpointer 表和全部记录内容。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from checkpointer_migration_utils import (  # noqa: E402
    MigrationError,
    compare_databases,
    configured_urls,
    connect,
)


def main() -> int:
    try:
        source_url, target_url = configured_urls()
        with connect(source_url) as source, connect(target_url) as target:
            results = compare_databases(source, target)
    except MigrationError as error:
        print(f"校验失败：{error}", file=sys.stderr)
        return 1
    except Exception as error:  # noqa: BLE001
        print(f"校验失败（{type(error).__name__}）。", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "verified",
                "schema_constraints_indexes_match": True,
                "all_row_content_hashes_match": True,
                "tables": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
