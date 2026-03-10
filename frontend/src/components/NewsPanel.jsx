import React from "react";
import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Chip from "@mui/material/Chip";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import NewspaperIcon from "@mui/icons-material/Newspaper";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

const SENTIMENT_COLORS = {
  Positive: "#00e676",
  Neutral: "#90a4ae",
  Negative: "#ff5252",
};

export default function NewsPanel({ news }) {
  if (!news) return null;

  const sentimentColor = SENTIMENT_COLORS[news.sentiment] || "#90a4ae";

  return (
    <Accordion>
      <AccordionSummary
        expandIcon={<ExpandMoreIcon sx={{ color: "text.secondary" }} />}
        sx={{
          px: 0,
          "& .MuiAccordionSummary-content": { alignItems: "center", gap: 1 },
        }}
      >
        <NewspaperIcon sx={{ fontSize: 16, color: "text.secondary" }} />
        <Typography variant="caption" color="text.secondary" fontWeight={600}>
          NEWS & SENTIMENT
        </Typography>
        <Chip
          label={news.sentiment}
          size="small"
          sx={{
            ml: "auto",
            height: 20,
            fontSize: "0.68rem",
            fontWeight: 700,
            color: sentimentColor,
            border: `1px solid ${sentimentColor}60`,
            background: `${sentimentColor}15`,
            mr: 1,
          }}
        />
      </AccordionSummary>
      <AccordionDetails sx={{ px: 0, pt: 0 }}>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
          {news.headlines?.slice(0, 6).map((item, idx) => (
            <Box
              key={idx}
              sx={{
                p: 1,
                borderRadius: 2,
                background: item.is_negative
                  ? "rgba(255,82,82,0.06)"
                  : "rgba(255,255,255,0.03)",
                border: item.is_negative
                  ? "1px solid rgba(255,82,82,0.2)"
                  : "1px solid rgba(255,255,255,0.05)",
                display: "flex",
                alignItems: "flex-start",
                gap: 1,
              }}
            >
              {item.is_negative && (
                <WarningAmberIcon
                  sx={{ fontSize: 14, color: "#ff5252", mt: 0.2, flexShrink: 0 }}
                />
              )}
              <Link
                href={item.link}
                target="_blank"
                rel="noopener"
                underline="hover"
                sx={{
                  fontSize: "0.75rem",
                  color: item.is_negative ? "#ff8a80" : "text.secondary",
                  lineHeight: 1.4,
                }}
              >
                {item.title}
              </Link>
            </Box>
          ))}
        </Box>
      </AccordionDetails>
    </Accordion>
  );
}
