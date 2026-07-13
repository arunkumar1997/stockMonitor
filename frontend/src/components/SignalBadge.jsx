import React from "react";
import Chip from "@mui/material/Chip";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import TrendingDownIcon from "@mui/icons-material/TrendingDown";
import RemoveIcon from "@mui/icons-material/Remove";
import DoNotDisturbAltIcon from "@mui/icons-material/DoNotDisturbAlt";
import AddShoppingCartIcon from "@mui/icons-material/AddShoppingCart";
import WatchLaterIcon from "@mui/icons-material/WatchLater";

const SIGNAL_CONFIG = {
  BUY: {
    icon: <TrendingUpIcon fontSize="small" />,
    sx: {
      background: "linear-gradient(135deg, #00e67622 0%, #00e67611 100%)",
      border: "1px solid #00e676",
      color: "#00e676",
      fontWeight: 800,
      fontSize: "0.82rem",
      letterSpacing: "1px",
    },
  },
  "BUY SMALL": {
    icon: <AddShoppingCartIcon fontSize="small" />,
    sx: {
      background: "linear-gradient(135deg, #69f0ae22 0%, #69f0ae11 100%)",
      border: "1px solid #69f0ae",
      color: "#69f0ae",
      fontWeight: 800,
      fontSize: "0.82rem",
      letterSpacing: "0.5px",
    },
  },
  WAIT: {
    icon: <WatchLaterIcon fontSize="small" />,
    sx: {
      background: "linear-gradient(135deg, #ffd74022 0%, #ffd74011 100%)",
      border: "1px solid #ffd740",
      color: "#ffd740",
      fontWeight: 800,
      fontSize: "0.82rem",
      letterSpacing: "1px",
    },
  },
  HOLD: {
    icon: <RemoveIcon fontSize="small" />,
    sx: {
      background: "linear-gradient(135deg, #ffd74022 0%, #ffd74011 100%)",
      border: "1px solid #ffd740",
      color: "#ffd740",
      fontWeight: 800,
      fontSize: "0.82rem",
      letterSpacing: "1px",
    },
  },
  AVOID: {
    icon: <DoNotDisturbAltIcon fontSize="small" />,
    sx: {
      background: "linear-gradient(135deg, #ff525244 0%, #ff525222 100%)",
      border: "1px solid #ff5252",
      color: "#ff5252",
      fontWeight: 800,
      fontSize: "0.82rem",
      letterSpacing: "1px",
    },
  },
};

function SignalBadge({ signal, confidence, size = "medium" }) {
  const cfg = SIGNAL_CONFIG[signal] || SIGNAL_CONFIG.WAIT;
  return (
    <Chip
      icon={cfg.icon}
      label={`${signal || "WAIT"} ${confidence ? `· ${confidence}%` : ""}`}
      size={size}
      sx={cfg.sx}
    />
  );
}

export default React.memo(SignalBadge);

