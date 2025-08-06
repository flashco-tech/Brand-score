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

### Required Python Packages
Create a `requirements.txt` file with:
```txt
langgraph
requests
serpapi
praw
twscrape
firecrawl-py
google-generativeai
python-dotenv
tqdm
fuzzywuzzy
asyncio
beautifulsoup4
ssl
socket
pathlib
concurrent.futures
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

# Twitter/X Accounts - Optional
username1=your_twitter_username1
password1=your_twitter_password1
email1=your_twitter_email1
email_pass1=your_email_password1

username2=your_twitter_username2
password2=your_twitter_password2
email2=your_twitter_email2
email_pass2=your_email_password2

# Firecrawl (Website Analysis) - Optional but recommended
FIRECRAWL_API_KEY=your_firecrawl_api_key
```

### 🔑 API Key Setup Guide

#### 1. 🔍 SerpAPI (Required)
- Sign up at [serpapi.com](https://serpapi.com)
- Get your API key from dashboard
- 💡 Free tier includes 100 searches/month

#### 2. 🤖 Google Gemini AI (Required)
- Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
- Create a new API key
- 💡 Free tier available with generous limits

#### 3. 💬 Reddit API (Optional)
- Create an app at [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
- Select "script" type application
- Note down client ID and secret

#### 4. 🐦 Twitter/X Accounts (Optional)
- Use existing Twitter accounts (2 recommended for better rate limits)
- Accounts should be verified and have access to the platform

#### 5. 🔥 Firecrawl (Optional)
- Sign up at [firecrawl.dev](https://firecrawl.dev)
- Get API key for enhanced website scraping
- 💡 Fallback to basic HTTP requests if not available

## 🚀 Usage

### Command Line Interface
```bash
python brand_analyzer.py
```

Follow the interactive prompts:
1. Enter brand name (required)
2. Enter Twitter handle (optional)
3. Enter website URL (optional)

### Programmatic Usage
```python
from brand_analyzer import BrandAnalyzer

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

### 🔒 Rate Limits
| Service | Free Tier Limit |
|---------|----------------|
| 🔍 SerpAPI | 100 searches/month |
| 🐦 Twitter | Account-dependent |
| 💬 Reddit | 60 requests/minute |
| 🤖 Gemini AI | Generous free limits |

### 🎯 Analysis Scope
- ✅ Focuses on online reputation and public information
- ❌ Cannot access private customer service records
- 🌍 Limited to English language content
- ⏰ May not capture very recent events (real-time limitations)

## 🔧 Troubleshooting

### 🚨 Common Issues

#### API Key Errors
```bash
❌ SERPAPI_KEY not found in environment variables
```
**💡 Solution**: Ensure `.env` file is properly configured with valid API keys

#### Network Timeouts
```bash
❌ Error fetching reviews: Connection timeout
```
**💡 Solution**: Check internet connection and API service status

#### Rate Limit Exceeded
```bash
❌ API rate limit exceeded
```
**💡 Solution**: Wait for rate limit reset or upgrade API plan

#### Empty Results
```bash
⚠️ No reviews collected
```
**💡 Solution**: Try different brand name variations or check if brand exists online

### 🐛 Debug Mode
Set environment variable for detailed logging:
```bash
export DEBUG=1
python brand_analyzer.py
```

## 🤝 Contributing

### 🛠️ Development Setup
1. 🍴 Fork the repository
2. 🐍 Create a virtual environment
3. 📦 Install development dependencies
4. 🧪 Run tests before submitting PRs

### 🔌 Adding New Data Sources
1. Create a new node function in the format `scrape_{source}_node`
2. Add to parallel collection workflow
3. Update trust scoring components if needed
4. Add appropriate error handling

### 📊 Extending Analysis Components
1. Add new analyzer method to `BrandTrustScorer`
2. Update component weights in `calculate_trust_score`
3. Add corresponding prompts for AI analysis

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚠️ Disclaimer

This tool is for research and informational purposes only. Trust scores are based on publicly available data and should not be the sole factor in business decisions. Always conduct additional due diligence before making purchases or business partnerships.

## 💬 Support

For issues and questions:
1. 🔍 Check the troubleshooting section
2. 📖 Review API documentation for external services
3. 🐛 Create an issue with detailed error logs and steps to reproduce

## 📝 Changelog

### Version 1.0.0
- ✨ Initial release with multi-source data collection
- 🤖 AI-powered trust scoring system
- 📊 Comprehensive reporting capabilities
- ⚡ Parallel processing for improved performance

---

<div align="center">

**🌟 Star this repository if you find it helpful!**

Made with ❤️ and 🤖 AI

</div>
