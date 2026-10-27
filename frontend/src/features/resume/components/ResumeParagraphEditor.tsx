import { documentFromText, documentToText, type TiptapDocument } from "../model/types";

export function ResumeParagraphEditor({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: TiptapDocument;
  disabled?: boolean;
  onChange: (document: TiptapDocument) => void;
}) {
  return (
    <label className="resume-field resume-field--full">
      <span>{label}</span>
      <textarea
        className="resume-textarea"
        disabled={disabled}
        maxLength={4_000}
        onChange={(event) => onChange(documentFromText(event.target.value))}
        rows={7}
        value={documentToText(value)}
      />
      <small>使用纯文本分段填写，每段单独成行，最多 4,000 个字符。</small>
    </label>
  );
}
