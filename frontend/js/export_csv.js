/**
 * SiliconRoute Decisions CSV Exporter
 * Downloads all recorded decisions as CSV from the live API.
 * docs/DESIGN_SPEC.md Section 6 & 10.
 */

export async function downloadDecisionsCsv() {
  try {
    const res = await fetch("/api/decisions?limit=500");
    if (!res.ok) {
      throw new Error(`Failed to fetch decisions: ${res.statusText}`);
    }
    const decisions = await res.json();
    if (!decisions || !decisions.length) {
      alert("No decisions available to export.");
      return;
    }

    const headers = [
      "id",
      "ts",
      "ai_model_id",
      "batch",
      "mode",
      "power_budget_w",
      "chosen_device_id",
      "explored",
      "reason",
      "actual_ms",
      "best_device_id_actual",
      "was_best",
      "regret_pct",
    ];

    const rows = [headers.join(",")];
    for (const d of decisions) {
      const row = headers.map((h) => {
        let val = d[h];
        if (val === null || val === undefined) val = "";
        val = String(val).replace(/"/g, '""');
        if (val.includes(",") || val.includes("\n") || val.includes('"')) {
          val = `"${val}"`;
        }
        return val;
      });
      rows.push(row.join(","));
    }

    const csvStr = rows.join("\n");
    const blob = new Blob([csvStr], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("data-test", "csv-download-link");
    link.download = `siliconroute_decisions_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error("Export CSV error:", err);
    alert("Export failed: " + err.message);
  }
}
