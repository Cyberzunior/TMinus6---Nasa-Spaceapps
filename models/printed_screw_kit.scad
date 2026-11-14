// T-Minus_6 printed screw kit
// Parametric M-style screws for FDM printing. Units: mm.
// Print head-down (flat head) or head-on-bed (pan head). No supports needed.
// Pitch is coarser than real M3 (0.6 vs 0.5) so the ridge survives layer lines.

$fn = 48;

// Helical thread: a circular bump twisted along the shaft (single start).
module printed_screw(d = 3.0, len = 10, head = "pan", pitch = 0.6, hexAF = 2.5) {
    rMaj  = d / 2;
    rBump = 0.35 * pitch;
    rCore = rMaj - rBump;                 // outer radius of the thread = rMaj
    headH = (head == "flat") ? 1.7 : 2.0; // flat head sits in the 6.4 mm / 1.8 mm countersink
    headD = (head == "flat") ? 6.0 : 5.5;
    shaftL = len - headH;
    hexDepth = 1.2;

    // Printed in use orientation: head on bed (z = 0), shaft grows up.
    if (head == "flat") {
        // Countersunk head: wide at the bed, tapering into the shaft.
        cylinder(h = headH, d1 = headD, d2 = d);
    } else {
        // Pan head: plain cylinder on the bed.
        cylinder(h = headH, d = headD);
    }

    // Threaded shaft, twisted profile.
    translate([0, 0, headH])
        linear_extrude(height = shaftL,
                       twist = -360 * shaftL / pitch,
                       slices = max(20, ceil(shaftL * 12)))
            union() {
                circle(r = rCore);
                translate([rCore, 0]) circle(r = rBump);
            }

    // Hex socket: on the head face, cut from the bed side (flat) or the head top (pan).
    if (head == "flat") {
        translate([0, 0, -0.01])
            cylinder(h = hexDepth + 0.01, d = hexAF / cos(30), $fn = 6);
    } else {
        translate([0, 0, headH - hexDepth])
            cylinder(h = hexDepth + 0.01, d = hexAF / cos(30), $fn = 6);
    }
}

// Washer-style spacer for the M3 x 8 pan + washer joint (printed as a ring).
module printed_washer(id = 3.4, od = 7, t = 0.8) {
    difference() {
        cylinder(h = t, d = od);
        translate([0, 0, -0.01]) cylinder(h = t + 0.02, d = id);
    }
}

// Kit layout on one bed. Quantities per the Printed Parts Assembly Guide, step 1 list:
//   M3x10 flat-head x28, M3x10 pan x10, M3x30 pan x4, M3x8 pan x2 (+2 washers),
//   M3x6 pan x8, M2.5x8 pan x4.  Print 2-4 spares of the flat-head.
module kit_preview() {
    translate([0,  0, 0]) printed_screw(3.0, 10, "flat");
    translate([10, 0, 0]) printed_screw(3.0, 10, "pan");
    translate([20, 0, 0]) printed_screw(3.0, 30, "pan");
    translate([30, 0, 0]) printed_screw(3.0, 8,  "pan");
    translate([40, 0, 0]) printed_washer();
    translate([50, 0, 0]) printed_screw(3.0, 6,  "pan");
    translate([60, 0, 0]) printed_screw(2.5, 8,  "pan", pitch = 0.5, hexAF = 2.0);
}

kit_preview();
