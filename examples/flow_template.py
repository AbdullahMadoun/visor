"""
A flow for `visor run`: one call of main() per target.

    visor run --flow examples/flow_template.py --targets targets.csv
    visor run --flow examples/flow_template.py --url https://example.com

Return nothing for success, "failed" for a failure, or raise visor.Skip("why").
Clicks that can't find their text are handled by the strategy tree / agent while this runs.
"""
import visor


def main(url):
    visor.goto(url)

    # Check for dead ends before doing any work
    if visor.see(["Page not found", "No longer available"]):
        raise visor.Skip("gone")

    # Accept a few wordings of the same button, and verify the result
    visor.click(["More information", "Learn more", "More info"], expect="Example Domains")
