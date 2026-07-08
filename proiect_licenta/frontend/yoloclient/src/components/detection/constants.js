export const MODES = [
  {
    id: "detection",
    labelKey: "modes.detection.label",
    sublabelKey: "modes.detection.sublabel",
    label: "YOLO Detection",
    sublabel: "Bounding boxes + tracking",
    color: "cyan",
    payload: { mode: "detection", dm_model: null }
  },
  {
    id: "crowd_qnrf",
    labelKey: "modes.crowd_qnrf.label",
    sublabelKey: "modes.crowd_qnrf.sublabel",
    label: "DM-Count QNRF",
    sublabel: "Scene diverse / aeriene",
    color: "emerald",
    payload: { mode: "crowd", dm_model: "qnrf" }
  },
  {
    id: "crowd_nwpu",
    labelKey: "modes.crowd_nwpu.label",
    sublabelKey: "modes.crowd_nwpu.sublabel",
    label: "DM-Count NWPU",
    sublabel: "Scene urbane dense",
    color: "teal",
    payload: { mode: "crowd", dm_model: "nwpu" }
  }
];

export const MODE_COLORS = {
  detection: { accent: "#00e676", accentAlpha: "#00e67620", border: "#00e67640" },
  crowd_qnrf: { accent: "#69f0ae", accentAlpha: "#69f0ae20", border: "#69f0ae40" },
  crowd_nwpu: { accent: "#00c853", accentAlpha: "#00c85320", border: "#00c85340" },
};

export const CHART_LEN = 60;

export const COLOR_CLASSES = {
  cyan:  { activeBorder: "border-cyan-400/60",   activeBg: "bg-cyan-400/10",   activeText: "text-cyan-400",   dot: "bg-cyan-400",   accentAlpha: "#00e67620" },
  emerald: { activeBorder: "border-emerald-400/60", activeBg: "bg-emerald-400/10", activeText: "text-emerald-400", dot: "bg-emerald-400", accentAlpha: "#69f0ae20" },
  teal:  { activeBorder: "border-teal-400/60",  activeBg: "bg-teal-400/10",  activeText: "text-teal-400",  dot: "bg-teal-400",  accentAlpha: "#00c85320" },
};