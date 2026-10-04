(function (root) {
    const LOAN_RATE_PERCENT = 9.5;
    const LOAN_YEARS = 5;
    const DEFAULT_DOWN_SHARE = 0.2;
    const DAYS_PER_MONTH = 365 / 12;
    const MAX_KM_PER_DAY = 500;

    function emiFor(loan, ratePercent, months) {
        if (loan <= 0) return 0;
        const r = ratePercent / 1200;
        if (r === 0) return loan / months;
        const f = Math.pow(1 + r, months);
        return loan * r * f / (f - 1);
    }

    function ownershipCost(car, kmPerDay, downPayment) {
        const price = Number(car.price);
        const perKm = Number(car.cost_per_km);
        const service = Number(car.service_cost);
        const km = Number(kmPerDay);
        if (![price, perKm, service, km].every(Number.isFinite) || price <= 0 || km <= 0 || km > MAX_KM_PER_DAY) return null;

        const asked = downPayment === null || downPayment === undefined || downPayment === "" ? null : Number(downPayment);
        if (asked !== null && (!Number.isFinite(asked) || asked < 0)) return null;

        const down = Math.min(asked === null ? price * DEFAULT_DOWN_SHARE : asked, price);
        const loan = price - down;
        const months = LOAN_YEARS * 12;
        const emi = emiFor(loan, LOAN_RATE_PERCENT, months);
        const fuelMonthly = km * DAYS_PER_MONTH * perKm;
        const total = down + emi * months + fuelMonthly * months + service * LOAN_YEARS;

        return { emi, fuelMonthly, service, total, down, loan, interest: emi * months - loan, hasLoan: loan > 0 };
    }

    const api = { ownershipCost, emiFor, LOAN_RATE_PERCENT, LOAN_YEARS, DEFAULT_DOWN_SHARE, MAX_KM_PER_DAY };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.Ownership = api;
})(typeof window !== "undefined" ? window : globalThis);
