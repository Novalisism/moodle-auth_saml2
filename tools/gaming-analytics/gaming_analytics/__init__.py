"""Gaming / YouTube analytics pipeline.

Answers two questions asked in review:

1. Where does "Player Scale" come from and what is the estimate logic?
   -> gaming_analytics.playerscale + METHODOLOGY.md. Every number carries its
      inputs, its method, its source URLs and a low/high band.

2. Rank the Key IPs by sales and by YouTube views.
   -> gaming_analytics.rank, fed by live Steam + YouTube Data API collectors.
"""

__version__ = "0.1.0"
