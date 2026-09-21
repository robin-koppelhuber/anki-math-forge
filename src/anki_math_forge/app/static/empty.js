/* The "nothing here yet" page.

   It extends the same base as the other views and so renders the same header,
   the same rails and the same footer legend -- but it overrode no `scripts`
   block, so `bindKeys` was never called and not one of the keys its footer
   listed did anything. The first screen anybody sees was the one that lied
   about how to drive it.

   Three keys, because three is what this page has: there is no deck, so
   nothing per-item has anything to act on. The footer is narrowed to match by
   `EMPTY_VIEW_KEYS` on the Python side, so the two cannot drift. */
bindKeys({
  filters: toggleFilters,
  // The shelf is a page now, not a dialog over this one.
  projects: () => (location.href = "/projects"),
  guide: cycleGuide,
});
