import { QRCodeSVG } from "qrcode.react";

import type { ChecklistSession } from "../types";

export function StaffHandoff({
  checklist,
  onClose,
}: {
  checklist: ChecklistSession;
  onClose: () => void;
}) {
  const checklistUrl = `${window.location.origin}/checklist/${checklist.token}`;
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="handoff-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="handoff-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="modal-close" type="button" onClick={onClose} aria-label="Close">×</button>
        <span className="kicker">Scoped staff access</span>
        <h2 id="handoff-title">Green Close handoff</h2>
        <p>
          Staff can scan this code to open only today’s closing checklist. The link expires in
          24 hours and contains no bill or financial data.
        </p>
        <div className="qr-frame">
          <QRCodeSVG
            value={checklistUrl}
            size={190}
            bgColor="#ffffff"
            fgColor="#0b1711"
            level="M"
            title="Staff checklist QR code"
          />
        </div>
        <div className="handoff-meta">
          <div><span>Tasks</span><strong>{checklist.tasks.length}</strong></div>
          <div><span>Access</span><strong>Checklist only</strong></div>
          <div><span>Expires</span><strong>{new Date(checklist.expires_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</strong></div>
        </div>
        <label className="share-link">
          <span>Shareable link</span>
          <input readOnly value={checklistUrl} onFocus={(event) => event.target.select()} />
        </label>
      </section>
    </div>
  );
}
