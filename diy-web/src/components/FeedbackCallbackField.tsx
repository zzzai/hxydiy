import { useId, useState } from 'react';
import { validCallbackPhone } from '../visitFeedback';

type Props = { value: string; disabled: boolean; onChange: (value: string) => void };

export default function FeedbackCallbackField({ value, disabled, onChange }: Props) {
  const id = useId();
  const [touched, setTouched] = useState(false);
  const invalid = touched && !validCallbackPhone(value);
  return <div className="feedback-callback">
    <label htmlFor={id}>回访手机号 <small>选填</small></label>
    <input id={id} type="tel" inputMode="tel" autoComplete="tel-national" placeholder="11位手机号"
      value={value} disabled={disabled} aria-invalid={invalid} aria-describedby={id + '-hint'}
      onBlur={() => setTouched(true)} onChange={event => onChange(event.target.value)} />
    <small id={id + '-hint'} aria-live="polite">{invalid
      ? '请输入有效的11位手机号，或留空提交。'
      : '希望店长联系您？留下手机号，仅用于本次评价回访。'}</small>
  </div>;
}
