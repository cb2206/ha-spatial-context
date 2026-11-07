import { describe, expect, it, vi } from "vitest";
import {
  PANEL_BUNDLE_PATH,
  panelBundleUrls,
  reloadFresh,
} from "./reload-fresh";

const docWith = (srcs: string[]) =>
  ({
    querySelectorAll: () => srcs.map((src) => ({ src })),
  }) as unknown as Pick<Document, "querySelectorAll">;

describe("panelBundleUrls", () => {
  it("includes the bare path and each loaded bundle URL, nothing else", () => {
    const urls = panelBundleUrls(
      docWith([
        "https://ha.local:8123/frontend_latest/app.js",
        "https://ha.local:8123/spatial_context_panel.js?v=1794070000",
      ]),
    );
    expect(urls).toEqual([
      PANEL_BUNDLE_PATH,
      "https://ha.local:8123/spatial_context_panel.js?v=1794070000",
    ]);
  });

  it("falls back to the bare path when no script matches", () => {
    expect(panelBundleUrls(docWith([]))).toEqual([PANEL_BUNDLE_PATH]);
  });
});

describe("reloadFresh", () => {
  it("refetches every URL with cache: reload before reloading", async () => {
    const order: string[] = [];
    const fetchFn = vi.fn(async (url: string, init: RequestInit) => {
      expect(init.cache).toBe("reload");
      order.push(`fetch ${url}`);
    });
    await reloadFresh(["/a.js", "/b.js?v=1"], fetchFn, () =>
      order.push("reload"),
    );
    expect(order).toEqual(["fetch /a.js", "fetch /b.js?v=1", "reload"]);
  });

  it("still reloads when a fetch fails", async () => {
    const reload = vi.fn();
    await reloadFresh(
      ["/a.js"],
      async () => {
        throw new Error("offline");
      },
      reload,
    );
    expect(reload).toHaveBeenCalledOnce();
  });
});
