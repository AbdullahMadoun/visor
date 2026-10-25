"""
Visor quickstart: open a page, read it, and move around by visible text.

    python examples/quickstart.py
"""
import visor

visor.goto("https://news.ycombinator.com")
print("\n".join(visor.read()[:8]))     # the top of the page, as Visor sees it

visor.click("new")                     # the "new" link in the header
visor.click("More")                    # scrolls down to the link at the bottom by itself
print("Now at:", visor.current_url())

visor.close()
