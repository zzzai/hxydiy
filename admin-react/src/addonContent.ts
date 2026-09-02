export type AddonForm = {
  chargeable?: boolean;
  store_price?: number | null;
  member_price?: number | null;
  member_price_enabled?: boolean;
};

const toCents = (value: number | null | undefined) => Math.round(Number(value || 0) * 100);

export function addonFormPayload(form: AddonForm & Record<string, unknown>) {
  const chargeable = form.chargeable !== false;
  const storePrice = toCents(form.store_price);
  const memberPriceEnabled = chargeable && form.member_price_enabled === true;
  return {
    ...form,
    chargeable,
    store_price_cents: chargeable ? storePrice : 0,
    member_price_cents: memberPriceEnabled ? toCents(form.member_price) : null,
    member_price_enabled: memberPriceEnabled,
  };
}

export function addonToForm(addon: Record<string, any>) {
  return {
    ...addon,
    store_price: Number(addon.store_price_cents || 0) / 100,
    member_price: addon.member_price_enabled ? Number(addon.member_price_cents || 0) / 100 : null,
  };
}
