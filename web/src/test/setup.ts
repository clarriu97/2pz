import "@testing-library/jest-dom/vitest";

// jsdom implements no scrolling at all, so `Element.scrollTo` is missing.
// Real browsers have had it for a decade; this is an environment gap rather
// than something the product should be defensive about.
if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = () => {};
}
