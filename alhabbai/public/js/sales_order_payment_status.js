frappe.ui.form.on("Sales Order", {
    refresh(frm) {
        // Refresh header indicator dynamically
        set_payment_status_indicator(frm);
    },
    onload_post_render(frm) {
        // Also handle on load (before refresh triggers sometimes)
        set_payment_status_indicator(frm);
    },
});

function set_payment_status_indicator(frm) {
    if (!frm || frm.is_new()) return;

    const customStatus = frm.doc.custom_payment_status || "Pending";
    const nativeStatus = frm.doc.payment_status || "Unpaid";

    // Map colors
    const colorMap = {
        "Fully Paid": "green",
        "Paid": "green",
        "Partially Paid": "orange",
        "Partly Paid": "orange",
        "Pending": "red",
        "Unpaid": "red",
    };

    const color = colorMap[customStatus] || colorMap[nativeStatus] || "gray";

    // Create nice display text (combine both statuses if different)
    let displayText =
        customStatus === nativeStatus
            ? customStatus
            : `${customStatus} (${nativeStatus})`;

    frm.page.set_indicator(displayText, color);

    // Optional small console debug (remove in production)
    console.log(
        `🔹 Payment Indicator: ${displayText} | Color: ${color}`
    );
}
