/**
 * SiliconRoute Design Spec v2 — API Client
 * Clean REST and SSE wrappers for backend services.
 */

export const api = {
  async get(url) {
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      throw new Error(err.detail || `Request failed with status ${res.status}`);
    }
    return res.json();
  },

  async post(url, data) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      throw new Error(err.detail || `Request failed with status ${res.status}`);
    }
    return res.json();
  },

  fetchPublishedMetrics() {
    return this.get("/api/published-metrics");
  },

  fetchSystemInfo() {
    return this.get("/api/system");
  },

  fetchDevices() {
    return this.get("/api/devices");
  },

  fetchModels() {
    return this.get("/api/models");
  },

  fetchScalingData(family = "mlp", batch = 1) {
    return this.get(`/api/analysis/chart-data?family=${family}&batch=${batch}`);
  },

  fetchCrossoverData() {
    return this.get("/api/analysis/crossovers-all");
  },

  fetchFits() {
    return this.get("/api/fits");
  },

  fetchSessionVariability() {
    return this.get("/api/analysis/variability");
  },

  fetchWakeColdSummary() {
    return this.get("/api/analysis/cold-start");
  },

  fetchPhysicsNotes() {
    return this.get("/api/analysis/physics-notes");
  },

  fetchEvaluation() {
    return this.get("/api/decisions/evaluation");
  },

  fetchDecisions(limit = 10, offset = 0) {
    return this.get(`/api/decisions?limit=${limit}&offset=${offset}`);
  },

  fetchRun(runId) {
    return this.get(`/api/runs/${runId}`);
  },

  routeModel(payload) {
    return this.post("/api/route", payload);
  },

  connectTelemetryStream(onSample, onError) {
    const evtSource = new EventSource("/api/telemetry/stream");
    evtSource.onmessage = (event) => {
      try {
        const sample = JSON.parse(event.data);
        if (onSample) onSample(sample);
      } catch (err) {
        console.error("Telemetry JSON parse error:", err);
      }
    };
    evtSource.onerror = (err) => {
      if (onError) onError(err);
    };
    return evtSource;
  },
};
