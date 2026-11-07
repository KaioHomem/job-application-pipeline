#!/usr/bin/env python3
"""The funnel as an MCP server.

The only file in this repository with a dependency outside the standard
library. Everything that decides an answer lives in `tools.py` and is tested
without starting a server; this file is transport and nothing else.

The directory is `mcp_server/`, not `mcp/`, because a local package named
`mcp` would shadow the SDK of the same name on the import path.

    pip install -r mcp_server/requirements.txt

    python mcp_server/server.py          # stdio, for a local client
    python mcp_server/server.py --http   # streamable HTTP on 0.0.0.0:$PORT

See docs/DECISIONS.md #5 for why this dependency exists and what it costs.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from mcp_server.tools import (  # noqa: E402
    funnel_summary as _funnel_summary,
    screen_posting as _screen_posting,
    simulate_profile as _simulate_profile,
    why_skipped as _why_skipped,
)

INSTRUCTIONS = """\
A real job hunt, as data you can interrogate.

Nine hard filters screened 189 job postings over seven days in September 2026.
This server exposes what happened and lets you re-run the decision under a
different candidate.

Two datasets, with different powers:

  the record    189 postings. Counts and reason codes only. It cannot be
                re-screened: the tracker never stored each posting's shift,
                work model or required technology.
  the detailed set
                21 postings whose every field was recovered, so they can be
                screened again under an edited profile.

Nothing here is a prediction. Every number is computed from committed data.
"""

server = MCPServer("job-application-pipeline", instructions=INSTRUCTIONS)


@server.tool()
def funnel_summary() -> dict:
    """Counts over the whole record: status, first filter to fire, and what the record cannot answer."""
    return _funnel_summary()


@server.tool()
def why_skipped(code: str) -> dict:
    """List the postings a given filter stopped first.

    Codes: closed, affirmative, location, schedule, seniority, degree, field,
    tech, experience, salary, unattributed.
    """
    return _why_skipped(code)


@server.tool()
def simulate_profile(changes: dict | None = None) -> dict:
    """Re-screen the detailed set under an edited candidate profile.

    `changes` may set any of: availability ({"start": "08:00", "end": "18:00"}),
    min_monthly_salary, max_seniority, accepts_remote, onsite_cities, tech_years.
    Anything omitted keeps its real value. Returns what the change freed and
    what it cost.
    """
    return _simulate_profile(changes)


@server.tool()
def screen_posting(posting: dict, changes: dict | None = None) -> dict:
    """Run the nine filters over a posting you describe.

    `posting` needs at least work_model (remote, hybrid or onsite). It may also
    carry title, city, country, schedule, seniority, required_tech,
    required_years, requires_completed_degree, accepted_fields, monthly_salary,
    affirmative_only and closed.
    """
    return _screen_posting(posting, changes)


@server.custom_route("/health", methods=["GET"])
async def health(request):  # noqa: ANN001, ARG001 — starlette passes the request
    """A plain GET for a platform health check.

    `/mcp` is not one. The streamable-HTTP endpoint rejects a bare GET that
    carries no session and no event-stream Accept header, so a health check
    pointed at it reports a perfectly healthy service as down. It also reads
    the record, so a container that starts without its data fails the check
    instead of serving empty answers.
    """
    from starlette.responses import JSONResponse

    return JSONResponse(
        {
            "ok": True,
            "server": server.name,
            "tools": ["funnel_summary", "why_skipped", "simulate_profile", "screen_posting"],
            "postings_in_record": _funnel_summary()["total_postings"],
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()

    if args.http:
        # Stateless, so any number of instances can sit behind one address and
        # a restart never strands a client mid-session.
        server.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            stateless_http=True,
        )
    else:
        server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
