import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { confirmUtilityBill, uploadUtilityBill } from "../api";
import type { UtilityBill } from "../types";

export function BillUpload({
  projectId,
  onConfirmed,
}: {
  projectId: string;
  onConfirmed: (bill: UtilityBill) => void;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<UtilityBill | null>(null);
  const [values, setValues] = useState({ period_start: "", period_end: "", total_kwh: 0, total_cost_sgd: 0 });
  const upload = useMutation({
    mutationFn: (file: File) => uploadUtilityBill(projectId, file),
    onSuccess: (bill) => {
      setDraft(bill);
      setValues({
        period_start: bill.period_start,
        period_end: bill.period_end,
        total_kwh: bill.total_kwh,
        total_cost_sgd: bill.total_cost_sgd,
      });
    },
  });
  const confirm = useMutation({
    mutationFn: () => confirmUtilityBill(projectId, draft!.id, values),
    onSuccess: (bill) => {
      onConfirmed(bill);
      setDraft(null);
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      void queryClient.invalidateQueries({ queryKey: ["run"] });
    },
  });

  if (draft) {
    return (
      <form className="bill-review" onSubmit={(event) => { event.preventDefault(); confirm.mutate(); }}>
        <div className="bill-review-heading"><div><span>Review extracted fields</span><strong>{draft.filename}</strong></div><small>Raw file discarded</small></div>
        <label><span>Period start</span><input type="date" required value={values.period_start} onChange={(event) => setValues({ ...values, period_start: event.target.value })} /></label>
        <label><span>Period end</span><input type="date" required value={values.period_end} onChange={(event) => setValues({ ...values, period_end: event.target.value })} /></label>
        <label><span>Consumption (kWh)</span><input type="number" min="0.01" step="0.01" required value={values.total_kwh} onChange={(event) => setValues({ ...values, total_kwh: Number(event.target.value) })} /></label>
        <label><span>Total cost (SGD)</span><input type="number" min="0.01" step="0.01" required value={values.total_cost_sgd} onChange={(event) => setValues({ ...values, total_cost_sgd: Number(event.target.value) })} /></label>
        <div className="bill-review-actions"><button type="button" onClick={() => setDraft(null)}>Cancel</button><button className="primary" type="submit" disabled={confirm.isPending}>{confirm.isPending ? "Confirming…" : "Confirm fields"}</button></div>
      </form>
    );
  }

  return (
    <label className="bill-upload">
      <span className="upload-icon">＋</span>
      <span><strong>{upload.isPending ? "Parsing bill…" : "Use your own utility bill"}</strong><small>PDF, JSON, CSV, or TXT · 5 MB maximum · review required</small></span>
      <input
        type="file"
        accept=".pdf,.json,.csv,.txt,application/pdf,application/json,text/csv,text/plain"
        disabled={upload.isPending}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) upload.mutate(file);
          event.target.value = "";
        }}
      />
      {upload.error && <em>{upload.error.message}</em>}
    </label>
  );
}
