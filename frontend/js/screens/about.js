/**
 * SiliconRoute Design Spec v2 — About Screen (Section 6.7)
 * Mission, system architecture, honest limitations from README,
 * AI assistance disclosure, and MIT license.
 */

export class AboutScreen {
  constructor(apiClient) {
    this.api = apiClient;
    this.isLoaded = false;
  }

  async init() {
    // Static content rendered with .metric tags
  }

  async onActivate() {
    // No dynamic fetching needed beyond metrics component resolution
  }
}
