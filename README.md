# 🎯 Brand Trust Analysis System


A comprehensive automated system for analyzing brand trustworthiness using multi-source data collection and AI-powered scoring.

## 🚀 Overview

The Brand Trust Analysis System collects data from multiple online sources to evaluate brand credibility, customer satisfaction, and overall trustworthiness. It provides a comprehensive trust score (0-10) with detailed component analysis and actionable insights.

## ✨ Features

### 🔍 Multi-Source Data Collection
- **🛒 Google Product Reviews**: Scrapes product reviews, ratings, and customer feedback
- **💬 Reddit Analysis**: Collects brand mentions and discussions across relevant subreddits
- **🐦 Twitter/X Monitoring**: Analyzes brand mentions and social media sentiment
- **🌐 Website Trust Assessment**: Evaluates SSL certificates, contact information, and professional presentation

### 🤖 AI-Powered Analysis
- **📊 Trust Scoring**: Component-based scoring system using Google's Gemini AI
- **💭 Sentiment Analysis**: Natural language processing of reviews and social mentions
- **✅ Legitimacy Assessment**: Website and business credibility evaluation
- **🎧 Customer Support Analysis**: Service quality assessment from available data

### 📋 Comprehensive Reporting
- Overall trust score with detailed breakdown
- Component-wise analysis with weighted contributions
- Key strengths and areas of concern identification
- JSON export for further analysis

## 🛠️ Installation

### Prerequisites
- Python 3.8 or higher
- API keys for various services (see Configuration section)

### Install Dependencies
```bash
git clone https://github.com/yourusername/brand-trust-analysis.git
cd brand-score
pip install -r requirements.txt
```


## ⚙️ Configuration

Create a `.env` file in the project root with the following API keys:

### Required APIs
```env
# Google Search (SerpAPI) - Required for Google Reviews
SERPAPI_KEY=your_serpapi_key

# Google Gemini AI - Required for analysis
GEMINI_API_KEY=your_gemini_api_key

# Reddit API - Optional but recommended
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=brand_reviews_scraper/1.0

# Twitter/X Accounts 
username1=your_twitter_username1
password1=your_twitter_password1
email1=your_twitter_email1
email_pass1=your_email_password1

username2=your_twitter_username2
password2=your_twitter_password2
email2=your_twitter_email2
email_pass2=your_email_password2

# Firecrawl (Website Analysis) 
FIRECRAWL_API_KEY=your_firecrawl_api_key
```

## 🚀 Usage

### Command Line Interface
```bash
python langraph_1.py
```

Follow the interactive prompts:
1. Enter brand name (required)
2. Enter Twitter handle (optional)
3. Enter website URL (optional)

### Programmatic Usage
```python
from langraph_1 import BrandAnalyzer

# Initialize analyzer
analyzer = BrandAnalyzer()

# Run analysis
result = analyzer.analyze_brand(
    brand_name="Example Brand",
    twitter_handle="@examplebrand",  # optional
    website="https://example.com"    # optional
)

# Access results
trust_score = result["trust_score"]["final_score"]
recommendation = result["trust_score"]["score_interpretation"]
```

## 📊 Output Format

### 🏆 Trust Score Components

The system evaluates 5 key components with weighted importance:

| Component | Weight | Description |
|-----------|--------|-------------|
| **🏅 Ratings** | 55% | Product ratings and review volume from Google |
| **💭 Review Sentiment** | 20% | Overall sentiment analysis from all sources |
| **✅ Business Legitimacy** | 10% | Website trust indicators and professionalism |
| **📱 Social Media** | 10% | Social media presence and mention analysis |
| **🎧 Customer Support** | 5% | Support quality based on customer feedback |

### 📈 Score Interpretation

| Score Range | Rating | Description |
|-------------|--------|-------------|
| **8.5-10.0** | 🌟 Excellent | Strong buy confidence |
| **7.0-8.4** | ✅ Good | Generally trustworthy |
| **5.5-6.9** | ⚠️ Average | Proceed with research |
| **4.0-5.4** | ⚡ Below Average | Significant concerns |
| **0-3.9** | ❌ Poor | High risk, consider alternatives |

### 📄 Output Files

The system generates a detailed JSON report:
```json
{brand_name}_analysis.json
```

**Contains:**
- ✅ Complete trust score breakdown
- 📊 Raw data from all sources
- 🔍 Component analysis results
- 📈 Data collection status
- ⚠️ Error logs and warnings

## 🏗️ System Architecture

### 🔄 Workflow Structure
1. **🔍 Input Validation**: Validates brand name and optional parameters
2. **⚡ Parallel Data Collection**: Simultaneously collects data from all sources
3. **🤖 Trust Scoring**: AI-powered analysis using Google Gemini
4. **📊 Report Generation**: Creates comprehensive analysis report

### 🛡️ Error Handling
- ✅ Graceful fallback when APIs are unavailable
- 📊 Partial analysis when some data sources fail
- 📝 Detailed error logging for troubleshooting

## ⚠️ Limitations

### 📊 Data Source Limitations
- **🛒 Google Reviews**: Limited to publicly available product reviews
- **💬 Reddit**: Depends on public subreddit discussions
- **🐦 Twitter/X**: Subject to platform rate limits and account restrictions
- **🌐 Website Analysis**: Limited to publicly accessible pages



Made with ❤️ by Akshay Kumar


