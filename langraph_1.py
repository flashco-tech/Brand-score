import json
import os
import asyncio
import time
import re
import random
import ssl
import socket
from urllib.parse import urlparse
from typing import Dict, Any, List, Optional, TypedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from dotenv import load_dotenv
import requests
from serpapi import GoogleSearch
from tqdm import tqdm
from fuzzywuzzy import fuzz
import praw
from twscrape import AccountsPool, API
from firecrawl import FirecrawlApp

load_dotenv()

# ========================
# STATE DEFINITION
# ========================

class BrandAnalysisState(TypedDict):
    """State structure for the brand analysis workflow"""
    brand_name: str
    twitter_handle: Optional[str]
    website: Optional[str]
    
    # Data collection results
    google_reviews: List[Dict[str, Any]]
    reddit_reviews: List[Dict[str, Any]]
    # twitter_data: Dict[str, Any]
    website_trust_data: Dict[str, Any]
    
    # Analysis results
    trust_score: Optional[Dict[str, Any]]
    final_report: Optional[Dict[str, Any]]
    
    # Status tracking
    collection_status: Dict[str, str]
    errors: List[str]

# ========================
# GOOGLE REVIEWS NODE
# ========================

def fetch_reviews(product_id: str, min_pages: int = 1, max_pages: int = 1) -> Dict[str, Any]:
    """Fetch reviews for a specific product from Google with improved pagination."""
    all_reviews = []
    overall_ratings = None
    page_count = 0
    

    params = {
        "engine": "google_product",
        "product_id": product_id,
        "google_domain": "google.com",
        "gl": "in",
        "hl": "en",
        "location": "India",
        "reviews": "1",
        "api_key": os.getenv("SERPAPI_KEY"),
        "sort_by": "relevance"  # Try different sorting
    }

    print(f"  📊 Fetching reviews for product ID: {product_id}")

    # Modified to fetch only the first page
    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        page_count = 1

        # Extract overall ratings on first page
        product_results = results.get("product_results", {})
        reviews_results = results.get("reviews_results", {})
        
        overall_ratings = {
            "average_rating": product_results.get("rating"),
            "total_reviews": product_results.get("reviews"),
            "ratings_breakdown": reviews_results.get("ratings", []),
            "product_title": product_results.get("title", "")
        }
        
        print(f"    📈 Product: {overall_ratings['product_title']}")
        print(f"    ⭐ Rating: {overall_ratings['average_rating']}, Reviews: {overall_ratings['total_reviews']}")

        # Extract reviews from first page
        reviews = results.get("reviews_results", {}).get("reviews", [])
        page_reviews_count = len(reviews)
        
        if page_reviews_count == 0:
            print(f"    ⚠️  No reviews found on page 1")
            # Try different sort orders if no reviews
            for sort_order in ["most_relevant", "newest", "oldest", "highest_rating", "lowest_rating"]:
                params["sort_by"] = sort_order
                search = GoogleSearch(params)
                results = search.get_dict()
                reviews = results.get("reviews_results", {}).get("reviews", [])
                if reviews:
                    print(f"    ✅ Found {len(reviews)} reviews with sort: {sort_order}")
                    break

        # Process reviews
        for r in reviews:
            review_data = {
                "date": r.get("date"),
                "rating": r.get("rating"),
                "source": r.get("source"),
                "content": r.get("content", ""),
                "images": r.get("images", []),
                "helpful_count": r.get("helpful_count"),
                "user": r.get("user", {})
            }
            # Only add reviews with content
            if review_data["content"] and len(review_data["content"].strip()) > 10:
                all_reviews.append(review_data)

        print(f"    📄 Page 1: Found {page_reviews_count} reviews, Total: {len(all_reviews)}")
        
    except Exception as e:
        print(f"    ❌ Error fetching reviews for page 1: {e}")

    print(f"  📊 Total reviews collected: {len(all_reviews)} from 1 page")
    return {
        "product_id": product_id,
        "overall_rating": overall_ratings,
        "reviews": all_reviews,
        "pages_scraped": page_count
    }

def search_products(brand: str, max_products: int = 50) -> List[Dict[str, Any]]:
    """Search for products with multiple search strategies."""
    all_products = []
    
    # Multiple search strategies - expanded for more coverage
    search_queries = [
        brand,
        f"{brand}"
    ]
    
    for query in search_queries:
        print(f"  🔍 Searching: '{query}'")
        
        # Try multiple pages for each query - increased num for more results
        params = {
            "engine": "google_shopping",
            "google_domain": "google.com",
            "q": query,
            "start": "1",
            "num": "3",  
            "hl": "en",
            "gl": "in",
            "location": "India",
            "api_key": os.getenv("SERPAPI_KEY")
        }

        search = GoogleSearch(params)
        results = search.get_dict()
        products = extract_products(results, brand)
        print(f"    📦 Found {len(products)} relevant products")
                
        all_products.extend(products)
        
        time.sleep(random.uniform(1, 2))
        
        if len(all_products) >= max_products * 2:  # Get more products initially
            break
    
    # Remove duplicates based on product_id
    unique_products = {}
    for product in all_products:
        pid = product.get("product_id")
        if pid and pid not in unique_products:
            unique_products[pid] = product
    
    return list(unique_products.values())

from typing import List, Dict, Any

def extract_products(data: Dict[str, Any], brand: str) -> List[Dict[str, Any]]:
    """Extract products with relaxed brand filtering to get more results."""
    products = []

    # Normalize brand once
    brand_lower = brand.lower()
    brand_words = brand_lower.split()  # Split brand into words for partial matching

    for item in data.get("shopping_results", []):
        title = item.get("title", "").lower()
        source = item.get("source", "")
        source_name = source.get("name", "") if isinstance(source, dict) else str(source)
        source_name_lower = source_name.lower()

        # ✅ Relaxed matching: brand name OR any brand word in title or source
        brand_match = False
        if brand_lower in title or brand_lower in source_name_lower:
            brand_match = True
        else:
            # Check for partial word matches
            for word in brand_words:
                if len(word) > 2 and (word in title or word in source_name_lower):
                    brand_match = True
                    break

        if brand_match:
            rating = item.get("rating")
            reviews_count = item.get("reviews")

            # Safe rating conversion
            try:
                rating = float(rating) if rating is not None else None
            except (ValueError, TypeError):
                rating = None

            # Safe review count conversion
            try:
                reviews_count = int(reviews_count) if reviews_count is not None else 0
            except (ValueError, TypeError):
                reviews_count = 0

            # Simple quality score
            quality_score = 0
            if rating is not None:
                quality_score += rating * 10
            if reviews_count > 0:
                quality_score += min(reviews_count, 100)

            product_data = {
                "product_name": item.get("title"),
                "product_id": item.get("product_id"),
                "rating": rating,
                "reviews": reviews_count,
                "link": item.get("link"),
                "price": item.get("price"),
                "brand_match_score": 100,  # Fixed, since it matched our criteria
                "quality_score": quality_score,
                "source": source_name,
                "thumbnail": item.get("thumbnail")
            }
            products.append(product_data)

    return products


def select_best_products(products: List[Dict[str, Any]], max_products: int = 10) -> List[Dict[str, Any]]:
    """Select products in 3 groups: 10 best rated + 10 worst rated + 10 most reviewed."""
    
    # Filter out products without product_id
    valid_products = [p for p in products if p.get("product_id")]
    
    if not valid_products:
        return []
    
    # Separate products with ratings from those without
    products_with_ratings = [p for p in valid_products if p.get("rating") is not None]
    products_without_ratings = [p for p in valid_products if p.get("rating") is None]
    
    selected_products = []
    used_product_ids = set()
    
    # Group 1: Top 10 best rated products
    if products_with_ratings:
        best_rated = sorted(products_with_ratings, 
                          key=lambda x: (x.get("rating", 0), x.get("reviews", 0)), 
                          reverse=True)[:10]
        
        for product in best_rated:
            if product.get("product_id") not in used_product_ids:
                selected_products.append(product)
                used_product_ids.add(product.get("product_id"))
        
        print(f"    ⭐ Selected {len([p for p in best_rated if p.get('product_id') not in used_product_ids or p.get('product_id') in [sp.get('product_id') for sp in selected_products]])} best rated products")
    
    # Group 2: Top 10 worst rated products (but still with ratings)
    if products_with_ratings and len(products_with_ratings) > 1:
        worst_rated = sorted(products_with_ratings, 
                           key=lambda x: (x.get("rating", 5), -x.get("reviews", 0)), 
                           reverse=False)[:10]
        
        group2_added = 0
        for product in worst_rated:
            if product.get("product_id") not in used_product_ids:
                selected_products.append(product)
                used_product_ids.add(product.get("product_id"))
                group2_added += 1
        
        print(f"    📉 Selected {group2_added} worst rated products")
    
    # Group 3: Top 10 most reviewed products (regardless of rating)
    all_products_sorted_by_reviews = sorted(valid_products, 
                                          key=lambda x: x.get("reviews", 0), 
                                          reverse=True)[:10]
    
    group3_added = 0
    for product in all_products_sorted_by_reviews:
        if product.get("product_id") not in used_product_ids:
            selected_products.append(product)
            used_product_ids.add(product.get("product_id"))
            group3_added += 1
    
    print(f"    💬 Selected {group3_added} most reviewed products")
    
    # If we still don't have enough products, add remaining valid products
    if len(selected_products) < max_products:
        remaining_needed = max_products - len(selected_products)
        remaining_products = [p for p in valid_products 
                            if p.get("product_id") not in used_product_ids]
        
        # Sort remaining by quality score
        remaining_products.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
        
        for product in remaining_products[:remaining_needed]:
            selected_products.append(product)
            used_product_ids.add(product.get("product_id"))
    
    print(f"    ✅ Total selected: {len(selected_products)} products")
    return selected_products[:max_products]

def process_brand_reviews(brand_name: str) -> List[Dict[str, Any]]:
    """Process reviews for a specific brand with improved strategy."""
    print(f"\n🚀 Starting comprehensive review collection for: {brand_name}")
    
    # Search for products with multiple strategies
    print("🔍 Phase 1: Product Discovery")
    all_products = search_products(brand_name, max_products=50)
    
    if not all_products:
        print(f"❌ No products found for {brand_name}")
        return []

    print(f"📦 Found {len(all_products)} total products")
    
    # Select best products for review scraping
    selected_products = select_best_products(all_products, max_products=10)
    print(f"✅ Selected {len(selected_products)} products for review scraping")
    
    # Display selected products
    print("\n📋 Selected Products:")
    for i, product in enumerate(selected_products, 1):
        print(f"  {i}. {product.get('product_name', 'Unknown')[:60]}...")
        print(f"     Rating: {product.get('rating', 'N/A')}, Reviews: {product.get('reviews', 'N/A')}")
        print(f"     Brand Match: {product.get('brand_match_score', 0)}%, Source: {product.get('source', 'N/A')}")

    # Fetch reviews for selected products
    print(f"\n🔄 Phase 2: Review Collection")
    brand_reviews = []
    
    for i, product in enumerate(tqdm(selected_products, desc="Fetching reviews"), 1):
        try:
            product_id = product.get("product_id")
            if not product_id:
                continue
                
            print(f"\n📊 Product {i}/{len(selected_products)}: {product.get('product_name', 'Unknown')[:50]}...")
            
            # With this safe version:
            def get_page_limits_based_on_reviews(product):
                expected_reviews = product.get("reviews", 0)
                
                # Handle None values
                if expected_reviews is None:
                    expected_reviews = 0
                
                try:
                    expected_reviews = int(expected_reviews)
                except (ValueError, TypeError):
                    expected_reviews = 0
                
                if expected_reviews > 500:
                    return 8, 20
                elif expected_reviews > 100:
                    return 5, 15
                else:
                    return 3, 10

            # Then use it like this:
            min_pages, max_pages = get_page_limits_based_on_reviews(product)
                
            review_data = fetch_reviews(product_id, min_pages=min_pages, max_pages=max_pages)
            review_data["product_name"] = product.get("product_name")
            review_data["brand_match_score"] = product.get("brand_match_score")
            review_data["source"] = product.get("source")
            
            if review_data.get("reviews"):
                brand_reviews.append(review_data)
                print(f"    ✅ Collected {len(review_data['reviews'])} reviews")
            else:
                print(f"    ⚠️  No reviews collected")
                
            # Progressive rate limiting
            sleep_time = random.uniform(3, 6) if i < 5 else random.uniform(2, 4)
            time.sleep(sleep_time)
            
        except Exception as e:
            print(f"    ❌ Failed for {product.get('product_name', 'Unknown')}: {e}")
            continue

    # Summary
    total_reviews = sum(len(product.get("reviews", [])) for product in brand_reviews)
    print(f"\n📈 Collection Summary:")
    print(f"   Products processed: {len(brand_reviews)}")
    print(f"   Total reviews: {total_reviews}")
    print(f"   Average reviews per product: {total_reviews/len(brand_reviews) if brand_reviews else 0:.1f}")

    return brand_reviews

def scrape_google_reviews_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node for scraping Google product reviews with enhanced error handling."""
    print("🎯 [Google Reviews] Starting comprehensive product review scraping...")
    
    try:
        brand_name = state.get("brand_name")
        if not brand_name:
            print("❌ No brand name provided")
            return {**state, "google_reviews": []}
        
        # Check API key
        if not os.getenv("SERPAPI_KEY"):
            print("❌ SERPAPI_KEY not found in environment variables")
            return {**state, "google_reviews": []}
            
        reviews = process_brand_reviews(brand_name)
        
        if reviews:
            print(f"✅ Successfully collected reviews for {len(reviews)} products")
        else:
            print("⚠️  No reviews collected")
            
        return {**state, "google_reviews": reviews}
        
    except Exception as e:
        print(f"❌ Error in Google reviews node: {e}")
        import traceback
        traceback.print_exc()
        return {**state, "google_reviews": []}

# ========================
# REDDIT REVIEWS NODE
# ========================

reddit_client = None

def initialize_reddit_client():
    """Initialize Reddit client with credentials from environment variables."""
    global reddit_client
    try:
        reddit_client = praw.Reddit(
            client_id=os.getenv("REDDIT_CLIENT_ID"),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
            user_agent=os.getenv("REDDIT_USER_AGENT", "brand_reviews_scraper/1.0")
        )
        print("Reddit client initialized successfully")
    except Exception as e:
        print(f"Failed to initialize Reddit client: {e}")
        reddit_client = None

def google_subreddit_search(query: str, k: int = 10) -> List[str]:
    """Find relevant subreddits for the brand."""
    if not os.getenv("SERPAPI_KEY"):
        return []

    params = {
        "q": f"{query} site:reddit.com",
        "api_key": os.getenv("SERPAPI_KEY"),
        "engine": "google",
        "num": k,
        "gl": "in",
        "hl": "en",
    }
    
    try:
        resp = requests.get("https://serpapi.com/search.json", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        pattern = re.compile(r"/r/([A-Za-z0-9_]+)", re.IGNORECASE)
        seen = set()
        subreddits = []
        
        for result in data.get("organic_results", []):
            text_candidates = [result.get("link", ""), result.get("title", "")]
            for text in text_candidates:
                for match in pattern.findall(text):
                    if match.lower() not in seen:
                        seen.add(match.lower())
                        subreddits.append(match)
                        if len(subreddits) >= k:
                            return subreddits
        
        return subreddits
    except Exception as e:
        print(f"Error during subreddit search: {e}")
        return []

def fetch_reddit_reviews(product_query: str) -> List[Dict[str, Any]]:
    """Fetch Reddit reviews for a brand."""
    if not reddit_client:
        return []
    
    subreddits = google_subreddit_search(product_query, k=5)
    if not subreddits:
        return []

    structured_data = []

    try:
        for subreddit_name in subreddits:
            try:
                subreddit = reddit_client.subreddit(subreddit_name)
                time.sleep(1)
                
                for submission in subreddit.search(product_query, sort='relevance', limit=3):
                    if product_query.lower() not in (submission.title + submission.selftext).lower():
                        continue

                    try:
                        submission.comments.replace_more(limit=0)
                        comments_data = []

                        for comment in submission.comments.list()[:3]:
                            if (comment.body and 
                                comment.body not in ['[deleted]', '[removed]'] and 
                                len(comment.body.strip()) > 10):
                                
                                comments_data.append({
                                    "score": comment.score,
                                    "body": comment.body.strip(),
                                    "created_utc": comment.created_utc
                                })

                        post_data = {
                            "subreddit": subreddit.display_name,
                            "post_title": submission.title,
                            "post_score": submission.score,
                            "post_text": submission.selftext,
                            "comments": comments_data
                        }
                        structured_data.append(post_data)
                        
                    except Exception as e:
                        print(f"Error processing submission: {e}")
                        continue
                        
            except Exception as e:
                print(f"Error processing subreddit '{subreddit_name}': {e}")
                continue
                
    except Exception as e:
        print(f"Error during Reddit data extraction: {e}")

    return structured_data

def scrape_reddit_reviews_node(state: BrandAnalysisState) -> BrandAnalysisState:
    """LangGraph node for scraping Reddit reviews."""
    print("[Reddit] Scraping Reddit reviews...")
    
    try:
        if not reddit_client:
            initialize_reddit_client()
            
        brand_name = state.get("brand_name")
        if not brand_name:
            return {**state, "reddit_reviews": []}
            
        reviews = fetch_reddit_reviews(brand_name)
        return {**state, "reddit_reviews": reviews}
    except Exception as e:
        print(f"Error in Reddit reviews node: {e}")
        return {**state, "reddit_reviews": []}

# ========================
# TWITTER NODE
# ========================

# async def initialize_twitter_api() -> Optional[API]:
#     """Initialize Twitter API with account pool."""
#     try:
#         pool = AccountsPool()
        

#         username1 = os.getenv("username1")
#         password1 = os.getenv("password1")
#         email1 = os.getenv("email1")
#         email_pass1 = os.getenv("email_pass1")

#         username2 = os.getenv("username2")
#         password2 = os.getenv("password2")
#         email2 = os.getenv("email2")
#         email_pass2 = os.getenv("email_pass2")
        
#         await pool.add_account(username1, password1, email1, email_pass1)
#         await pool.add_account(username2, password2, email2, email_pass2)
#         await pool.login_all()
#         print("✅ Twitter API initialized")
#         return API(pool)
        
#     except Exception as e:
#         print(f"❌ Error initializing Twitter API: {e}")
#         return None

# async def scrape_twitter_data(brand_handle: str) -> Dict[str, List[Dict[str, Any]]]:
#     """Scrape Twitter data for a brand."""
#     api = await initialize_twitter_api()
#     if not api:
#         return {"brand_own": [], "mentions": []}
    
#     brand_own = []
#     mentions = []
    
#     try:
#         # Get user info
#         user = await api.user_by_login(brand_handle)
#         print(f"✅ Found Twitter user: @{brand_handle}")
        
#         # Get brand's own tweets (limited)
#         tweet_count = 0
#         async for tweet in api.user_tweets_and_replies(user.id, limit=50):
#             if tweet_count >= 20:  # Limit to prevent long waits
#                 break
                
#             brand_own.append({
#                 "id": tweet.id,
#                 "content": tweet.rawContent,
#                 "created_at": str(tweet.date),
#                 "likes": tweet.likeCount,
#                 "retweets": tweet.retweetCount,
#             })
#             tweet_count += 1
#             await asyncio.sleep(1)
        
#         # Get mentions (limited)
#         mention_count = 0
#         async for tweet in api.search(f"@{brand_handle}", limit=20):
#             if mention_count >= 10:  # Limit mentions
#                 break
                
#             if tweet.user.username.lower() != brand_handle.lower():
#                 mentions.append({
#                     "id": tweet.id,
#                     "username": tweet.user.username,
#                     "content": tweet.rawContent,
#                     "created_at": str(tweet.date),
#                     "likes": tweet.likeCount,
#                 })
#                 mention_count += 1
            
#             await asyncio.sleep(1)
            
#     except Exception as e:
#         print(f"Error scraping Twitter data: {e}")
    
#     return {"brand_own": brand_own, "mentions": mentions}

# def scrape_twitter_mentions_node(state: BrandAnalysisState) -> BrandAnalysisState:
#     """LangGraph node for scraping Twitter mentions."""
#     print("[Twitter] Scraping tweets and mentions...")
    
#     try:
#         twitter_handle = state.get("twitter_handle")
#         brand_name = state.get("brand_name", "")
        
#         # Try to derive handle from brand name if not provided
#         if not twitter_handle:
#             twitter_handle = brand_name.lower().replace(" ", "_").replace(".", "")
        
#         if twitter_handle:
#             twitter_handle = twitter_handle.lstrip('@')
#             twitter_data = asyncio.run(scrape_twitter_data(twitter_handle))
#             return {**state, "twitter_data": twitter_data}
#         else:
#             return {**state, "twitter_data": {"brand_own": [], "mentions": []}}
            
#     except Exception as e:
#         print(f"❌ Error in Twitter node: {e}")
#         return {**state, "twitter_data": {"brand_own": [], "mentions": []}}

# ========================
# WEBSITE ANALYSIS NODE
# ========================

import requests
def check_ssl_certificate(url: str) -> Dict[str, Any]:
    """Enhanced SSL certificate check with detailed information."""
    ssl_info = {
        "status": "Not checked",
        "https_enabled": False,
        "certificate_valid": False,
        "error": None
    }
    
    try:
        # First, try a simple HTTPS request
        response = requests.get(url, timeout=10, verify=True)
        if response.url.startswith("https://"):
            ssl_info["https_enabled"] = True
            ssl_info["certificate_valid"] = True
            ssl_info["status"] = "Valid TLS certificate (HTTPS enabled)"
        else:
            ssl_info["status"] = "No HTTPS (redirected to HTTP)"
            
    except requests.exceptions.SSLError as e:
        ssl_info["https_enabled"] = True  # HTTPS attempted but failed
        ssl_info["error"] = str(e)
        
        # Try to get more details about the SSL issue
        try:
            # Parse domain from URL
            domain = urlparse(url).netloc
            
            # Try connecting directly to get SSL info
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            with socket.create_connection((domain, 443), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert = ssock.getpeercert()
                    if cert:
                        ssl_info["status"] = "Certificate exists but verification failed"
                    else:
                        ssl_info["status"] = "No certificate found"
        except Exception:
            ssl_info["status"] = "SSL connection failed"
            
    except requests.exceptions.ConnectionError:
        # Try HTTP version
        try:
            http_url = url.replace("https://", "http://")
            response = requests.get(http_url, timeout=10)
            ssl_info["status"] = "No HTTPS (HTTP only)"
        except Exception:
            ssl_info["status"] = "Website unreachable"
            ssl_info["error"] = "Connection failed"
            
    except Exception as e:
        ssl_info["error"] = str(e)
        ssl_info["status"] = f"SSL check failed: {str(e)}"
    
    return ssl_info

def extract_contact_info(markdown_content: str) -> Dict[str, Any]:
    """Enhanced contact information extraction."""
    if not markdown_content:
        return {
            "phone": None, "address": None, "email": None,
            "phones_found": [], "addresses_found": [], "emails_found": []
        }
    
    # Enhanced phone patterns for Indian and international numbers
    phone_patterns = [
        r'(?:\+91|91)?[\s-]?[6-9]\d{9}',  # Indian mobile
        r'\(?\+91\)?[\s-]?[6-9][0-9]{4}[\s-]?[0-9]{5}',  # Indian with formatting
        r'\+\d{1,3}[\s-]?\d{6,14}',  # International
        r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',  # US format
        r'\(\d{3}\)\s?\d{3}[-.\s]?\d{4}',  # US with parentheses
    ]
    
    phones = []
    for pattern in phone_patterns:
        matches = re.findall(pattern, markdown_content)
        phones.extend([match.strip() for match in matches])
    
    # Remove duplicates and clean phone numbers
    phones = list(set([re.sub(r'[^\d+]', '', phone) for phone in phones if len(re.sub(r'[^\d]', '', phone)) >= 10]))
    
    # Enhanced address patterns
    address_patterns = [
        r'(?:address|registered\s+office|head\s+office|contact\s+us|location|office)[:\s\n]+([^\n]{20,300})',
        r'(?:find\s+us|visit\s+us|our\s+office)[:\s\n]+([^\n]{20,200})',
        r'(?:\d+[,\s]+[A-Za-z\s]+(?:street|road|lane|avenue|blvd|plaza|complex)[^.]{10,200})',
    ]
    
    addresses = []
    for pattern in address_patterns:
        matches = re.findall(pattern, markdown_content, re.IGNORECASE | re.MULTILINE)
        addresses.extend([match.strip() for match in matches])
    
    # Email patterns
    email_patterns = [
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        r'(?:email|contact|write\s+to)[:\s]+([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})',
    ]
    
    emails = []
    for pattern in email_patterns:
        matches = re.findall(pattern, markdown_content, re.IGNORECASE)
        emails.extend([match.strip() for match in matches])
    
    # Clean and deduplicate
    emails = list(set([email.lower() for email in emails if '@' in email and '.' in email]))
    addresses = list(set([addr[:200] for addr in addresses if len(addr.strip()) > 15]))
    
    return {
        "phone": phones[0] if phones else None,
        "address": addresses[0] if addresses else None,
        "email": emails[0] if emails else None,
        "phones_found": phones[:3],  # Keep top 3
        "addresses_found": addresses[:2],  # Keep top 2
        "emails_found": emails[:3]  # Keep top 3
    }

def detect_page_sections(markdown_content: str) -> Dict[str, Any]:
    """Detect various page sections and trust indicators."""
    if not markdown_content:
        return {}
    
    lower_content = markdown_content.lower()
    
    # Enhanced About Us detection
    about_keywords = [
        "about us", "about", "about-", "our story", "who we are", "company", 
        "founder", "brand story", "our mission", "our vision", "history",
        "established", "founded", "team", "leadership", "our journey",
        "why we", "what we do", "company profile", "brand profile"
    ]
    
    # Privacy Policy detection
    privacy_keywords = [
        "privacy policy", "privacy", "data protection", "cookie policy",
        "data privacy", "personal information", "data collection",
        "privacy notice", "privacy statement", "gdpr", "data usage"
    ]
    
    # Support/Customer Service detection
    support_keywords = [
        "support", "customer service", "help", "faq", "contact", "customer care",
        "help center", "support center", "assistance", "customer support",
        "help desk", "service", "live chat", "get help", "need help"
    ]
    
    # Terms and Conditions
    terms_keywords = [
        "terms", "terms and conditions", "terms of service", "terms of use",
        "legal", "disclaimer", "conditions", "agreement", "user agreement"
    ]
    
    # Social Media detection
    social_patterns = {
        "instagram": [r'instagram\.com/[\w.]+', r'@[\w.]+.*instagram', r'insta\s*[:@]', r'ig\s*[:@]'],
        "twitter": [r'twitter\.com/[\w.]+', r'@[\w.]+.*twitter', r'x\.com/[\w.]+', r'twitter\s*[:@]'],
        "facebook": [r'facebook\.com/[\w.]+', r'fb\.com/[\w.]+', r'facebook\s*[:@]', r'fb\s*[:@]'],
        "linkedin": [r'linkedin\.com/[\w./]+', r'linkedin\s*[:@]'],
        "youtube": [r'youtube\.com/[\w./]+', r'youtu\.be/[\w.]+', r'youtube\s*[:@]']
    }
    
    # Check for each section type
    sections = {
        "about_us": {
            "found": any(keyword in lower_content for keyword in about_keywords),
            "keywords_found": [kw for kw in about_keywords if kw in lower_content]
        },
        "privacy_policy": {
            "found": any(keyword in lower_content for keyword in privacy_keywords),
            "keywords_found": [kw for kw in privacy_keywords if kw in lower_content]
        },
        "support": {
            "found": any(keyword in lower_content for keyword in support_keywords),
            "keywords_found": [kw for kw in support_keywords if kw in lower_content]
        },
        "terms": {
            "found": any(keyword in lower_content for keyword in terms_keywords),
            "keywords_found": [kw for kw in terms_keywords if kw in lower_content]
        },
        "social_media": {
            "platforms_found": [],
            "links_found": []
        }
    }
    
    # Social media detection
    for platform, patterns in social_patterns.items():
        for pattern in patterns:
            matches = re.findall(pattern, markdown_content, re.IGNORECASE)
            if matches:
                sections["social_media"]["platforms_found"].append(platform)
                sections["social_media"]["links_found"].extend(matches[:2])  # Limit matches
                break
    
    sections["social_media"]["found"] = len(sections["social_media"]["platforms_found"]) > 0
    
    return sections

def fetch_website_content(website: str, max_retries: int = 3) -> Optional[str]:
    """Fetch website content with multiple fallback strategies."""
    
    # Strategy 1: Try Firecrawl if API key available
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
    if firecrawl_key:
        for attempt in range(max_retries):
            try:
                print(f"  🔥 Trying Firecrawl (attempt {attempt + 1})...")
                firecrawl = FirecrawlApp(api_key=firecrawl_key)
                response = firecrawl.scrape_url(
                    website, 
                    formats=["markdown"], 
                    timeout=30000,
                    wait_for=2000  # Wait for page to load
                )
                
                if response and 'markdown' in response and response['markdown']:
                    print(f"  ✅ Firecrawl successful ({len(response['markdown'])} chars)")
                    return response['markdown']
                    
            except Exception as e:
                print(f"  ⚠️  Firecrawl attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
    
    # Strategy 2: Try direct requests with BeautifulSoup
    try:
        print(f"  🌐 Trying direct HTTP request...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(website, headers=headers, timeout=15, verify=False)
        response.raise_for_status()
        
        if response.text:
            # Basic HTML to text conversion
            import html
            text_content = html.unescape(response.text)
            # Remove HTML tags (basic)
            text_content = re.sub(r'<[^>]+>', ' ', text_content)
            text_content = re.sub(r'\s+', ' ', text_content).strip()
            
            if len(text_content) > 500:  # Ensure we got meaningful content
                print(f"  ✅ Direct request successful ({len(text_content)} chars)")
                return text_content
                
    except Exception as e:
        print(f"  ⚠️  Direct request failed: {e}")
    
    return None

def analyze_website_trust(brand_name: str, website: str) -> Dict[str, Any]:
    """Enhanced website trust analysis."""
    print(f"🔍 Analyzing website: {website}")
    
    if not website.startswith(('http://', 'https://')):
        website = f"https://{website}"
    
    trust_data = {
        "brand_name": brand_name,
        "website_url": website,
        "ssl_info": {},
        "contact_info": {},
        "page_sections": {},
        "trust_score": 0,
        "status": "Failed",
        "analysis_details": {}
    }
    
    # Enhanced SSL check
    print("  🔒 Checking SSL certificate...")
    trust_data["ssl_info"] = check_ssl_certificate(website)
    
    # Fetch website content with fallbacks
    print("  📄 Fetching website content...")
    markdown_content = fetch_website_content(website)
    
    if markdown_content:
        print(f"  ✅ Content fetched ({len(markdown_content)} characters)")
        
        # Extract contact information
        print("  📞 Extracting contact information...")
        trust_data["contact_info"] = extract_contact_info(markdown_content)
        
        # Detect page sections
        print("  📋 Detecting page sections...")
        trust_data["page_sections"] = detect_page_sections(markdown_content)
        
        # Store sample content for debugging
        trust_data["analysis_details"]["content_length"] = len(markdown_content)
        trust_data["analysis_details"]["content_sample"] = markdown_content[:500] + "..." if len(markdown_content) > 500 else markdown_content
    else:
        print("  ❌ Failed to fetch website content")
        trust_data["analysis_details"]["error"] = "Failed to fetch website content"
    
    # Calculate trust score
    trust_data["trust_score"] = calculate_trust_score(trust_data)
    
    # Determine status
    score = trust_data["trust_score"]
    if score >= 80:
        trust_data["status"] = "Excellent"
    elif score >= 60:
        trust_data["status"] = "Good"
    elif score >= 40:
        trust_data["status"] = "Partial"
    else:
        trust_data["status"] = "Failed"
    
    return trust_data

def calculate_trust_score(trust_data: Dict[str, Any]) -> int:
    """Calculate comprehensive trust score."""
    score = 0
    max_score = 100
    
    # SSL Certificate (25 points)
    ssl_info = trust_data.get("ssl_info", {})
    if ssl_info.get("certificate_valid"):
        score += 25
    elif ssl_info.get("https_enabled"):
        score += 10  # HTTPS attempted but issues
    
    # Contact Information (35 points total)
    contact_info = trust_data.get("contact_info", {})
    if contact_info.get("phone"):
        score += 15
    if contact_info.get("address"):
        score += 15
    if contact_info.get("email"):
        score += 5
    
    # Page Sections (30 points total)
    sections = trust_data.get("page_sections", {})
    if sections.get("about_us", {}).get("found"):
        score += 12
    if sections.get("privacy_policy", {}).get("found"):
        score += 8
    if sections.get("terms", {}).get("found"):
        score += 5
    if sections.get("support", {}).get("found"):
        score += 3
    if sections.get("social_media", {}).get("found"):
        score += 2
    
    # Content Quality Bonus (10 points)
    details = trust_data.get("analysis_details", {})
    content_length = details.get("content_length", 0)
    if content_length > 5000:
        score += 10
    elif content_length > 2000:
        score += 5
    elif content_length > 500:
        score += 2
    
    return min(score, 100)  # Cap at 100

def analyze_brand_website_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Enhanced LangGraph node for analyzing brand website."""
    print("🌐 [Website] Starting comprehensive website analysis...")
    
    try:
        brand_name = state.get("brand_name", "").strip()
        website = state.get("website", "").strip()
        
        if not brand_name:
            print("❌ No brand name provided")
            return {
                **state,
                "website_trust_data": {
                    "status": "Failed",
                    "error": "Missing brand name"
                }
            }
        
        if not website:
            print("⚠️  No website provided, skipping website analysis")
            return {
                **state,
                "website_trust_data": {
                    "status": "Skipped",
                    "error": "No website URL provided"
                }
            }
        
        print(f"🎯 Analyzing website for brand: {brand_name}")
        website_data = analyze_website_trust(brand_name, website)
        
        # Log summary
        score = website_data.get("trust_score", 0)
        status = website_data.get("status", "Unknown")
        print(f"✅ Website analysis complete - Score: {score}/100, Status: {status}")
        
        return {**state, "website_trust_data": website_data}
    
    except Exception as e:
        print(f"❌ Error in website analysis: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            **state,
            "website_trust_data": {
                "status": "Failed",
                "error": str(e),
                "trust_score": 0
            }
        }

# ========================
# TRUST SCORING SYSTEM
# ========================

import google.generativeai as genai

class BrandTrustScorer:
    """Trust scoring system using Gemini without expert opinion component"""

    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("gemini-2.5-pro")

    def _call_component_analyzer(self, prompt: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced component analyzer with better error handling and fallback"""
        if not self.model:
            print("  ⚠️  Gemini model not available, using fallback scoring")
            return self._fallback_scoring(data)
        
        try:
            # Prepare the input with length limit
            data_str = json.dumps(data, indent=2)[:1000]  # Limit data size
            full_prompt = f"{prompt}\n\nData to analyze:\n{data_str}"
        
            print(f"  🤖 Calling Gemini API (prompt length: {len(full_prompt)} chars)")
        
            # Generate content with timeout handling
            response = self.model.generate_content(
                full_prompt,
                generation_config={
                    "temperature": 0.3,
                    "top_p": 0.8,
                    "max_output_tokens": 1024
                }
            )
        
            if not response or not response.text:
                print("  ❌ Empty response from Gemini")
                return self._fallback_scoring(data)
        
            response_text = response.text.strip()
            print(f"  📥 Received response ({len(response_text)} chars)")
        
            # Enhanced JSON extraction
            # First try to find JSON block
            json_patterns = [
                r'```json\s*(\{.*?\})\s*```',  # JSON in code block
                r'```\s*(\{.*?\})\s*```',      # JSON in generic code block  
                r'(\{[^{}]*"[^"]*"[^{}]*:[^{}]*\})',  # Simple JSON pattern
                r'(\{.*\})'                     # Any curly braces content
            ]
        
            parsed_result = None
            for pattern in json_patterns:
                matches = re.findall(pattern, response_text, re.DOTALL)
                for match in matches:
                    try:
                        parsed_result = json.loads(match)
                        print(f"  ✅ Successfully parsed JSON using pattern")
                        break
                    except json.JSONDecodeError:
                        continue
                if parsed_result:
                    break       
            if parsed_result:
                return parsed_result
            else:
                print(f"  ⚠️  Could not parse JSON from response")
                print(f"  Response preview: {response_text[:200]}...")
                return self._fallback_scoring(data)
            
        except Exception as e:
            print(f"  ❌ Gemini API call failed: {e}")
            return self._fallback_scoring(data)

    def _fallback_scoring(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Improved fallback scoring with some basic logic"""
        # Try to extract some basic info for better fallback scores
        base_score = 5.5  # Slightly above middle
        
        # Adjust based on available data
        if isinstance(data, dict):
            if data.get("reviews_in_chunk", 0) > 10:
                base_score += 0.5  # More data available
            if data.get("total_reviews_analyzed", 0) > 50:
                base_score += 0.3  # Large dataset
        
        return {
            "review_sentiment_score": round(base_score, 1),
            "confidence_level": "Low",
            "key_factors": ["Fallback scoring - API unavailable", "Score estimated based on data volume"],
            "analysis_summary": {
                "total_reviews_analyzed": data.get("reviews_in_chunk", 0) if isinstance(data, dict) else 0,
                "sentiment_distribution": "Unable to analyze - using fallback",
                "major_themes": {"positive": [], "negative": []},
                "product_consistency": "Unable to determine",
                "severity_assessment": "API fallback mode"
            },
            "_fallback": True
        }
    def analyze_ratings(self, google_reviews: List[Dict]) -> Dict[str, Any]:
        """Analyze ratings component (50% weight)"""
        prompt = """Analyze the Google reviews data and provide a ratings score from 0-10.

Scoring Criteria:
- 9.0-10.0: 4.5+ average 
- 7.5-8.9: 4.0-4.4 average 
- 6.0-7.4: 3.5-3.9 average or inconsistent ratings
- 4.0-5.9: 3.0-3.4 average or concerning patterns
- 0-3.9: Below 3.0 average or very low volume

Return JSON: {"ratings_score": 7.8, "confidence_level": "High", "key_factors": ["factor1", "factor2"]}"""
        
        # Prepare simplified data
        total_reviews = 0
        total_rating = 0
        products = 0
        
        for product in google_reviews:
            if isinstance(product, dict) and "overall_rating" in product:
                overall = product["overall_rating"]
                if overall:
                    total_reviews += overall.get("total_reviews", 0)
                    if "average_rating" in overall:
                        total_rating += overall.get("average_rating", 0)
                        products += 1
        
        avg_rating = total_rating / products if products > 0 else 0
        
        data = {
            "total_reviews": total_reviews,
            "average_rating": avg_rating,
            "products_analyzed": products
        }
        
        return self._call_component_analyzer(prompt, data)
    
    def analyze_business_legitimacy(self, website_trust_data: Dict) -> Dict[str, Any]:
        """Analyze business legitimacy component (10% weight)"""
        prompt = """Analyze website trust data and provide a business legitimacy score from 0-10.

Scoring Criteria:
- 9.0-10.0: Exceptional professional website with SSL, contact info, address, about us
- 7.5-8.9: Strong professional presentation with most trust indicators
- 6.0-7.4: Adequate professionalism with basic indicators
- 4.0-5.9: Basic website with limited trust indicators
- 0-3.9: Poor presentation with major gaps

Return JSON: {"business_legitimacy_score": 8.2, "confidence_level": "High", "key_factors": ["factor1", "factor2"]}"""
        
        return self._call_component_analyzer(prompt, website_trust_data)
    

#     def analyze_review_sentiment(self, google_reviews: List[Dict], reddit_reviews: List[Dict]) -> Dict[str, Any]:
    
#         # Extract actual review text from the data structure
#         all_review_texts = []
        
#         # Process Google Reviews
#         for product_data in google_reviews:
#             if isinstance(product_data, dict) and "reviews" in product_data:
#                 for review in product_data["reviews"]:
#                     if isinstance(review, dict):
#                         content = review.get("content", "")
#                         rating = review.get("rating", 0)
#                         if content and len(content.strip()) > 10:
#                             all_review_texts.append({
#                                 "text": content,
#                                 "rating": rating,
#                                 "source": "Google"
#                             })
        
#         # Process Reddit Reviews
#         for reddit_post in reddit_reviews:
#             if isinstance(reddit_post, dict):
#                 # Add post content
#                 post_text = reddit_post.get("post_text", "")
#                 if post_text and len(post_text.strip()) > 10:
#                     all_review_texts.append({
#                         "text": post_text,
#                         "rating": "N/A",
#                         "source": "Reddit"
#                     })
                
#                 # Add comment content
#                 comments = reddit_post.get("comments", [])
#                 for comment in comments[:3]:  # Limit comments per post
#                     comment_text = comment.get("body", "")
#                     if comment_text and len(comment_text.strip()) > 10:
#                         all_review_texts.append({
#                             "text": comment_text,
#                             "rating": "N/A", 
#                             "source": "Reddit"
#                         })
        
#         print(f"  📝 Extracted {len(all_review_texts)} review texts for sentiment analysis")
        
#         # If no reviews found, return default
#         if not all_review_texts:
#             return {
#                 "review_sentiment_score": 5.0,
#                 "confidence_level": "Low",
#                 "key_factors": ["No review text available for sentiment analysis"],
#                 "analysis_summary": {
#                     "total_reviews_analyzed": 0,
#                     "sentiment_distribution": "No reviews available",
#                     "major_themes": {"positive": [], "negative": []},
#                     "product_consistency": "No data",
#                     "severity_assessment": "No reviews to assess"
#                 }
#             }
        
#         # Prepare review data for analysis (limit to avoid token limits)
#         google_reviews_text = ""
#         reddit_reviews_text = ""
        
#         # Take up to 50 reviews to avoid overwhelming the API
#         limited_reviews = all_review_texts
        
#         for review in limited_reviews:
#             review_line = f"Rating: {review['rating']}, Text: {review['text']}\n"
#             if review['source'] == 'Google':
#                 google_reviews_text += review_line
#             else:
#                 reddit_reviews_text += review_line
        
#         if not google_reviews_text:
#             google_reviews_text = "No Google reviews available"
#         if not reddit_reviews_text:
#             reddit_reviews_text = "No Reddit reviews available"
        
#         # Create the analysis prompt
#         prompt = f"""You are a Review Sentiment Specialist analyzing the emotional tone and themes in customer review text. timent on 0-10 scale.

#         REVIEWS DATA ({len(limited_reviews)} reviews):

#         Google Reviews: 
#         {google_reviews_text}

#         Reddit Reviews:
#         {reddit_reviews_text}



#         SENTIMENT SCORING FORMULA:

# Count sentiment expressions in review text:

# Positive language: "love", "amazing", "excellent", "great quality", "recommend"
# Negative language: "hate", "terrible", "poor", "disappointed", "waste of money"


# Calculate sentiment ratio:

# Reviews with positive sentiment / Total reviews with clear sentiment = X%


# Apply base score:

# 80%+ positive sentiment = 9.0-10.0
# 70-79% positive sentiment = 8.0-8.9
# 60-69% positive sentiment = 7.0-7.9
# 50-59% positive sentiment = 6.0-6.9
# 40-49% positive sentiment = 5.0-5.9
# 30-39% positive sentiment = 4.0-4.9
# Below 30% = 0-3.9


# Theme deductions (from text analysis):

# "Poor quality/cheap/flimsy" mentioned 15+ times: -1.0
# "Broke/fell apart/defective" mentioned 10+ times: -1.5
# "Terrible service/rude staff" mentioned 8+ times: -0.8"""

#         try:
#             # Call the LLM analyzer
#             result = self._call_component_analyzer(prompt, {
#                 "total_reviews": len(all_review_texts),
#                 "reviews_analyzed": len(limited_reviews)
#             })
            
#             if result and 'review_sentiment_score' in result:
#                 print(f"  ✅ Sentiment analysis complete: {result['review_sentiment_score']}")
#                 return result
#             else:
#                 print(f"  ⚠️  LLM analysis failed, using fallback")
#                 # Fallback scoring based on ratings
#                 return self._fallback_sentiment_scoring(limited_reviews)
                
#         except Exception as e:
#             print(f"  ❌ Error in sentiment analysis: {e}")
    
#     def analyze_social_media(self, twitter_data: Dict, reddit_reviews: List[Dict]) -> Dict[str, Any]:
#         """Analyze social media component (10% weight)"""
#         prompt = """Analyze social media data and provide a score from 0-10.

# Social media is inherently negative-biased. Score conservatively.

# Scoring Criteria:
# - 8.0-10.0: Positive mentions or minimal negative presence
# - 6.0-7.9: Normal negative bias, no extreme patterns
# - 4.0-5.9: Some concerning patterns
# - 2.0-3.9: Widespread negative patterns
# - 0-1.9: Extreme negative patterns

# Return JSON: {"social_media_score": 6.5, "confidence_level": "Medium", "key_factors": ["factor1", "factor2"]}"""
        
#         data = {
#             # "twitter_mentions": len(twitter_data.get("mentions", [])),
#             # "twitter_own_tweets": len(twitter_data.get("brand_own", [])),
#             "reddit_posts": len(reddit_reviews)
#         }
        
#         return self._call_component_analyzer(prompt, data)
    
    def analyze_customer_support(self, google_reviews: List[Dict], reddit_reviews: List[Dict]) -> Dict[str, Any]:
        """Analyze customer support component (10% weight)"""
        prompt = """Analyze customer support quality from available review data and provide a score from 0-10.

Scoring Criteria:
- 8.0-10.0: Few/no support complaints, evidence of good service
- 6.0-7.9: Some complaints but not overwhelming
- 4.0-5.9: Multiple support complaints
- 0-3.9: Widespread support complaints

Return JSON: {"customer_support_score": 7.2, "confidence_level": "Medium", "key_factors": ["factor1", "factor2"]}"""
        
        data = {
            "google_reviews_count": len(google_reviews),
            "reddit_posts_count": len(reddit_reviews),
            "total_data_points": len(google_reviews) + len(reddit_reviews)
        }
        
        return self._call_component_analyzer(prompt, data)
    
    def calculate_trust_score(self, state: BrandAnalysisState) -> Dict[str, Any]:
        """Calculate final trust score"""
        print("🔢 Calculating component scores...")
        
        weights = {
            'ratings': 0.50,
            'business_legitimacy': 0.15,
            'review_sentiment': 0.15,
            'social_media': 0.10,
            'customer_support': 0.10
        }
        
        component_scores = {}
        
        print("  Analyzing ratings...")
        component_scores['ratings'] = self.analyze_ratings(state.get("google_reviews", []))
        
        print("  Analyzing business legitimacy...")
        component_scores['business_legitimacy'] = self.analyze_business_legitimacy(state.get("website_trust_data", {}))
        
        print("  Analyzing review sentiment...")
        component_scores['review_sentiment'] = self.analyze_review_sentiment(
            state.get("google_reviews", []), 
            state.get("reddit_reviews", [])
        )
        
        print("  Analyzing social media...")
        component_scores['social_media'] = self.analyze_social_media(
            # state.get("twitter_data", {}),
            state.get("reddit_reviews", [])
        )
        
        print("  Analyzing customer support...")
        component_scores['customer_support'] = self.analyze_customer_support(
            state.get("google_reviews", []),
            state.get("reddit_reviews", [])
        )
        
        # Calculate final score
        scores = {}
        for component, weight in weights.items():
            component_result = component_scores.get(component, {})
            
            if 'error' in component_result:
                scores[component] = 5.0
            else:
                score_key = f"{component}_score"
                if score_key in component_result:
                    scores[component] = max(0.0, min(10.0, float(component_result[score_key])))
                else:
                    scores[component] = 5.0
        
        final_score = sum(scores[component] * weights[component] for component in weights.keys())
        
        def interpret_score(score):
            if score >= 8.5: return "Excellent - Strong buy confidence"
            elif score >= 7.0: return "Good - Generally trustworthy"
            elif score >= 5.5: return "Average - Proceed with research"
            elif score >= 4.0: return "Below Average - Significant concerns"
            else: return "Poor - High risk, consider alternatives"
        
        return {
            "final_score": round(final_score, 1),
            "component_breakdown": {
                component: {
                    "score": scores[component],
                    "weight": f"{int(weights[component]*100)}%",
                    "contribution": round(scores[component] * weights[component], 2)
                }
                for component in weights.keys()
            },
            "score_interpretation": interpret_score(final_score),
            "component_results": component_scores
        }

# ========================
# MAIN ANALYZER CLASS
# ========================

class BrandAnalyzer:
    """Main brand analysis orchestrator"""
    
    def __init__(self):
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """Build the LangGraph workflow"""
        workflow = StateGraph(BrandAnalysisState)
        
        # Add nodes
        workflow.add_node("input_validation", self.validate_input_node)
        workflow.add_node("parallel_data_collection", self.parallel_data_collection_node)
        workflow.add_node("trust_scoring", self.trust_scoring_node)
        workflow.add_node("generate_report", self.generate_report_node)
        
        # Define the flow
        workflow.set_entry_point("input_validation")
        workflow.add_edge("input_validation", "parallel_data_collection")
        workflow.add_edge("parallel_data_collection", "trust_scoring")
        workflow.add_edge("trust_scoring", "generate_report")
        workflow.add_edge("generate_report", END)
        
        # Compile with memory
        memory = MemorySaver()
        return workflow.compile(checkpointer=memory)
    
    def validate_input_node(self, state: BrandAnalysisState) -> BrandAnalysisState:
        """Validate and prepare input data"""
        print("🔍 Validating input data...")
        
        errors = []
        if not state.get("brand_name"):
            errors.append("Brand name is required")
        
        # Initialize status tracking
        collection_status = {
            "google_reviews": "pending",
            "reddit_reviews": "pending", 
            # "twitter_data": "pending",
            "website_analysis": "pending"
        }
        
        return {
            **state,
            "collection_status": collection_status,
            "errors": errors,
            "google_reviews": [],
            "reddit_reviews": [],
            # "twitter_data": {},
            "website_trust_data": {}
        }
    
    def parallel_data_collection_node(self, state: BrandAnalysisState) -> BrandAnalysisState:
        """Collect data from all sources in parallel"""
        print("🚀 Starting parallel data collection...")
        
        if state["errors"]:
            print("❌ Skipping data collection due to validation errors")
            return state
        
        # Define collection tasks
        def collect_google_reviews():
            try:
                print("📊 Collecting Google reviews...")
                result = scrape_google_reviews_node(state)
                return ("google_reviews", result.get("google_reviews", []), "completed")
            except Exception as e:
                print(f"❌ Google reviews failed: {e}")
                return ("google_reviews", [], f"failed: {str(e)}")
        
        def collect_reddit_reviews():
            try:
                print("🔍 Collecting Reddit reviews...")
                result = scrape_reddit_reviews_node(state)
                return ("reddit_reviews", result.get("reddit_reviews", []), "completed")
            except Exception as e:
                print(f"❌ Reddit reviews failed: {e}")
                return ("reddit_reviews", [], f"failed: {str(e)}")
        
        # def collect_twitter_data():
        #     try:
        #         print("🐦 Collecting Twitter data...")
        #         result = scrape_twitter_mentions_node(state)
        #         return ("twitter_data", result.get("twitter_data", {}), "completed")
        #     except Exception as e:
        #         print(f"❌ Twitter data failed: {e}")
        #         return ("twitter_data", {}, f"failed: {str(e)}")
        
        def collect_website_data():
            try:
                print("🌐 Analyzing website...")
                result = analyze_brand_website_node(state)
                return ("website_trust_data", result.get("website_trust_data", {}), "completed")
            except Exception as e:
                print(f"❌ Website analysis failed: {e}")
                return ("website_trust_data", {}, f"failed: {str(e)}")
        
        # Execute tasks in parallel
        # tasks = [collect_google_reviews, collect_reddit_reviews, collect_twitter_data, collect_website_data]
        tasks = [collect_google_reviews, collect_reddit_reviews, collect_website_data]
        results = {}
        collection_status = state["collection_status"].copy()
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_task = {executor.submit(task): task.__name__ for task in tasks}
            
            for future in as_completed(future_to_task):
                task_name = future_to_task[future]
                try:
                    key, data, status = future.result()
                    results[key] = data
                    collection_status[key] = status
                    print(f"✅ {task_name} completed: {status}")
                except Exception as e:
                    print(f"❌ {task_name} crashed: {e}")
        
        return {
            **state,
            **results,
            "collection_status": collection_status
        }
    
    def trust_scoring_node(self, state: BrandAnalysisState) -> BrandAnalysisState:
        """Calculate trust score based on collected data"""
        print("📊 Calculating trust score...")
        
        try:
            scorer = BrandTrustScorer()
            trust_score = scorer.calculate_trust_score(state)
            
            return {
                **state,
                "trust_score": trust_score
            }
        except Exception as e:
            print(f"❌ Trust scoring failed: {e}")
            return {
                **state,
                "trust_score": {"error": str(e), "final_score": 0.0},
                "errors": state["errors"] + [f"Trust scoring failed: {str(e)}"]
            }
    
    def generate_report_node(self, state: BrandAnalysisState) -> BrandAnalysisState:
        """Generate final analysis report with complete component data"""
        print("📝 Generating final report...")
        
        try:
            report_generator = ReportGenerator()
            final_report = report_generator.generate_comprehensive_report(state)
            
            # ADD: Ensure trust_score data is properly included
            trust_score = state.get("trust_score", {})
            if trust_score:
                final_report["trust_score_summary"] = {
                    "final_score": trust_score.get("final_score", 0),
                    "component_breakdown": trust_score.get("component_breakdown", {}),
                    "component_results": trust_score.get("component_results", {})
                }
            
        except Exception as e:
            print(f"❌ Report generation failed: {e}")
            final_report = {
                "error": str(e),
                "brand_name": state.get("brand_name", "Unknown"),
                "trust_score_summary": state.get("trust_score", {})
            }
            state = {
                **state,
                "errors": state.get("errors", []) + [f"Report generation failed: {str(e)}"]
            }
        
        # Always save JSON files with complete data
        filename = f"{state['brand_name'].lower().replace(' ', '_')}_analysis.json"
        
        # ADD: Enhanced data structure for JSON save
        complete_data = {
            **final_report,
            "complete_analysis_data": {
                "google_reviews_summary": {
                    "total_products": len(state.get("google_reviews", [])),
                    "total_reviews_collected": sum(len(product.get("reviews", [])) for product in state.get("google_reviews", []))
                },
                "reddit_data_summary": {
                    "total_posts": len(state.get("reddit_reviews", [])),
                    "subreddits_found": list(set([r.get("subreddit", "") for r in state.get("reddit_reviews", []) if r.get("subreddit")]))
                },
                # "twitter_data_summary": {
                #     "brand_tweets": len(state.get("twitter_data", {}).get("brand_own", [])),
                #     "mentions_found": len(state.get("twitter_data", {}).get("mentions", []))
                # },
                "website_analysis_summary": state.get("website_trust_data", {})
            }
        }
        
        self.save_json_files(filename, complete_data)

        return {
            **state,
            "final_report": final_report
        }
    
    def save_json_files(self, filename: str, data: Dict[str, Any]):
        """Save analysis results to JSON file"""
        try:
            with open(filename, "w") as f:
                json.dump(data, f, indent=2)
            print(f"💾 Analysis saved to: {filename}")
        except Exception as e:
            print(f"❌ Failed to save JSON file: {e}")

    def analyze_brand(self, brand_name: str, twitter_handle: str = None, website: str = None) -> Dict[str, Any]:
        """Main method to analyze a brand"""
        print(f"🎯 Starting analysis for brand: {brand_name}")
        
        # Create initial state
        initial_state = {
            "brand_name": brand_name,
            "twitter_handle": twitter_handle,
            "website": website,
        }
        
        # For now, run the workflow manually since LangGraph might not be available
        try:
            # Manual workflow execution
            state = self.validate_input_node(initial_state)
            state = self.parallel_data_collection_node(state)
            state = self.trust_scoring_node(state)
            final_state = self.generate_report_node(state)
            
            return final_state
        except Exception as e:
            print(f"❌ Analysis workflow failed: {e}")
            return {
                "brand_name": brand_name,
                "error": str(e),
                "trust_score": {"final_score": 0.0, "error": str(e)}
            }


class BrandTrustScorer:
    """Trust scoring system using Gemini without expert opinion component"""

    def __init__(self):
        # Check if API key is available
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("⚠️  Warning: GEMINI_API_KEY not found. Using fallback scoring.")
            self.model = None
        else:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel("gemini-1.5-pro")
            except Exception as e:
                print(f"⚠️  Warning: Failed to initialize Gemini model: {e}")
                self.model = None

    def _call_component_analyzer(self, prompt: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Call Gemini API with proper error handling"""
        if not self.model:
            # Fallback to basic scoring when Gemini is not available
            return self._fallback_scoring(data)
        
        try:
            # Prepare the input text
            input_text = prompt + "\n\nData to analyze:\n" + json.dumps(data, indent=2)[:3000]
            
            # Generate content
            response = self.model.generate_content(input_text)
            
            if not response or not response.text:
                print("⚠️  Empty response from Gemini")
                return self._fallback_scoring(data)
            
            response_text = response.text.strip()
            
            # Try to extract JSON from the response with better handling
            # First try to find complete JSON in code blocks
            json_patterns = [
                r'```json\s*(\{.*?\})\s*```',  # JSON in code block
                r'```\s*(\{.*?\})\s*```',      # JSON in generic code block
                r'(\{[^{}]*"[^"]*"[^{}]*:[^{}]*\})',  # Simple JSON pattern
                r'(\{.*\})'                     # Any curly braces content
            ]
            
            parsed_result = None
            for pattern in json_patterns:
                matches = re.findall(pattern, response_text, re.DOTALL)
                for match in matches:
                    try:
                        # Try to parse the JSON
                        parsed_result = json.loads(match)
                        break
                    except json.JSONDecodeError:
                        # If JSON is incomplete, try to fix common issues
                        try:
                            # Add missing closing braces/brackets
                            fixed_json = match
                            if fixed_json.count('{') > fixed_json.count('}'):
                                fixed_json += '}' * (fixed_json.count('{') - fixed_json.count('}'))
                            if fixed_json.count('[') > fixed_json.count(']'):
                                fixed_json += ']' * (fixed_json.count('[') - fixed_json.count(']'))
                            
                            # Try to parse the fixed JSON
                            parsed_result = json.loads(fixed_json)
                            print(f"  ✅ Fixed truncated JSON response")
                            break
                        except json.JSONDecodeError:
                            continue
                if parsed_result:
                    break
            
            if parsed_result:
                return parsed_result
            else:
                print(f"⚠️  Could not parse JSON from response")
                print(f"Response preview: {response_text[:300]}...")
                return self._fallback_scoring(data)
                
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing failed: {e}")
            print(f"Response was: {response_text[:200] if 'response_text' in locals() else 'No response'}")
            return self._fallback_scoring(data)
        except Exception as e:
            print(f"❌ Component analysis failed: {e}")
            return self._fallback_scoring(data)
    
    def _fallback_scoring(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback scoring when Gemini API fails"""
        return {
            "score": 6.0,
            "confidence_level": "Low",
            "key_factors": ["Fallback scoring due to API unavailability"],
            "method": "fallback"
        }
    
    def analyze_ratings(self, google_reviews: List[Dict]) -> Dict[str, Any]:
        """Analyze ratings component (50% weight - increased from 40%)"""
        prompt = """You are a Ratings Data Specialist. Analyze ONLY numerical rating data to assess product quality and customer satisfaction.

Scoring Criteria:
- 9.0-10.0: 4.5+ average consistent across products
- 7.5-8.9: 4.0-4.4 average mostly positive distribution
- 6.0-7.4: 3.5-3.9 average or inconsistent ratings across products
- 4.0-5.9: 3.0-3.4 average or concerning rating patterns
- 0-3.9: Below 3.0 average or very low review volume

Return JSON format:
{
  "ratings_score": 7.8,
  "confidence_level": "High",
  "key_factors": [
    "Average 4.2 rating across 479 total reviews indicates strong customer satisfaction",
    "70% of ratings are 4-5 stars showing predominantly positive experiences"
  ],
  "data_quality": "High volume provides reliable statistical base"
}"""
        
        # Prepare ratings data
        ratings_data = self._prepare_ratings_data(google_reviews)
        return self._call_component_analyzer(prompt, ratings_data)
    
    def analyze_business_legitimacy(self, website_trust_data: Dict) -> Dict[str, Any]:
        """Analyze business legitimacy component (15% weight - increased from 10%)"""
        prompt = """You are a Website Business Legitimacy Specialist. Analyze website trust indicators.

Scoring Criteria:
- 9.0-10.0: Exceptional professional website with comprehensive information, clear policies, strong trust signals
- 7.5-8.9: Strong professional presentation with good policy transparency and business information
- 6.0-7.4: Adequate professionalism with basic policies and business info
- 4.0-5.9: Basic website with limited policy transparency
- 0-3.9: Poor presentation with significant gaps in policies

Focus on: SSL certificate, contact info, physical address, about us page, professional presentation.

Return JSON format:
{
  "business_legitimacy_score": 8.2,
  "confidence_level": "High",
  "key_factors": [
    "Valid SSL certificate provides security",
    "Clear contact information available",
    "Professional website presentation"
  ],
  "trust_indicators": ["SSL", "Contact info", "Professional design"]
}"""
        
        return self._call_component_analyzer(prompt, website_trust_data)










    def analyze_review_sentiment(self, google_reviews: List[Dict], reddit_reviews: List[Dict]) -> Dict[str, Any]:
    
        # Extract actual review text from the data structure
        all_review_texts = []
        
        # Process Google Reviews
        for product_data in google_reviews:
            if isinstance(product_data, dict) and "reviews" in product_data:
                for review in product_data["reviews"]:
                    if isinstance(review, dict):
                        content = review.get("content", "")
                        rating = review.get("rating", 0)
                        if content and len(content.strip()) > 10:
                            all_review_texts.append({
                                "text": content,
                                "rating": rating,
                                "source": "Google"
                            })
        
        # Process Reddit Reviews
        for reddit_post in reddit_reviews:
            if isinstance(reddit_post, dict):
                # Add post content
                post_text = reddit_post.get("post_text", "")
                if post_text and len(post_text.strip()) > 10:
                    all_review_texts.append({
                        "text": post_text,
                        "rating": "N/A",
                        "source": "Reddit"
                    })
                
                # Add comment content
                comments = reddit_post.get("comments", [])
                for comment in comments[:3]:  # Limit comments per post
                    comment_text = comment.get("body", "")
                    if comment_text and len(comment_text.strip()) > 10:
                        all_review_texts.append({
                            "text": comment_text,
                            "rating": "N/A", 
                            "source": "Reddit"
                        })
        
        print(f"  📝 Extracted {len(all_review_texts)} review texts for sentiment analysis")
        
        # If no reviews found, return default
        if not all_review_texts:
            return {
                "review_sentiment_score": 5.0,
                "confidence_level": "Low",
                "key_factors": ["No review text available for sentiment analysis"],
                "analysis_summary": {
                    "total_reviews_analyzed": 0,
                    "sentiment_distribution": "No reviews available",
                    "major_themes": {"positive": [], "negative": []},
                    "product_consistency": "No data",
                    "severity_assessment": "No reviews to assess"
                }
            }
        
        # Prepare review data for analysis (limit to avoid token limits)
        google_reviews_text = ""
        reddit_reviews_text = ""
        
        # Take up to 50 reviews to avoid overwhelming the API
        limited_reviews = all_review_texts
        
        for review in limited_reviews:
            review_line = f"Rating: {review['rating']}, Text: {review['text']}\n"
            if review['source'] == 'Google':
                google_reviews_text += review_line
            else:
                reddit_reviews_text += review_line
        
        if not google_reviews_text:
            google_reviews_text = "No Google reviews available"
        if not reddit_reviews_text:
            reddit_reviews_text = "No Reddit reviews available"
        
        # Create the analysis prompt
        reviews_data = f"""REVIEWS DATA ({len(limited_reviews)} reviews):

        Google Reviews: 
        {google_reviews_text}

        Reddit Reviews:
        {reddit_reviews_text}"""
        
        prompt = f"""You are a Review Sentiment Specialist analyzing the emotional tone and themes in customer review text. Provide a sentiment score on 0-10 scale.

        {reviews_data}

        SENTIMENT SCORING FORMULA:

Count sentiment expressions in review text:

Positive language: "love", "amazing", "excellent", "great quality", "recommend"
Negative language: "hate", "terrible", "poor", "disappointed", "waste of money"

Calculate sentiment ratio:

Reviews with positive sentiment / Total reviews with clear sentiment = X%

Apply base score:

80%+ positive sentiment = 9.0-10.0
70-79% positive sentiment = 8.0-8.9
60-69% positive sentiment = 7.0-7.9
50-59% positive sentiment = 6.0-6.9
40-49% positive sentiment = 5.0-5.9
30-39% positive sentiment = 4.0-4.9
Below 30% = 0-3.9

Theme deductions (from text analysis):

"Poor quality/cheap/flimsy" mentioned 15+ times: -1.0
"Broke/fell apart/defective" mentioned 10+ times: -1.5
"Terrible service/rude staff" mentioned 8+ times: -0.8

Return in JSON format:
{{
  "review_sentiment_score": the calculated sentiment score based on analysis,
  "confidence_level": "High/Medium/Low",
  "key_factors": [
    "Brief explanation of main sentiment drivers",
    "Key themes found in reviews"
  ],
  "analysis_summary": {{
    "total_reviews_analyzed": {len(limited_reviews)},
    "positive_sentiment_percentage": the calculated positive sentiment percentage based on analysis,
    "negative_sentiment_percentage": the calculated negative sentiment percentage based on analysis,
    "major_themes": {{
      "positive": ["quality", "comfort"],
      "negative": ["sizing issues"]
    }}
  }}
}}
"""


        try:
            # Call the LLM analyzer
            result = self._call_component_analyzer(prompt, {
                "total_reviews": len(all_review_texts),
                "reviews_analyzed": len(limited_reviews)
            })
            
            if result and 'review_sentiment_score' in result:
                print(f"  ✅ Sentiment analysis complete: {result['review_sentiment_score']}")
                return result
            else:
                print(f"  ⚠️  LLM analysis failed, using fallback")
                # Fallback scoring based on ratings
                # return self._fallback_sentiment_scoring(limited_reviews)
                
        except Exception as e:
            print(f"  ❌ Error in sentiment analysis: {e}")
    
#     def analyze_social_media(self, twitter_data: Dict, reddit_reviews: List[Dict]) -> Dict[str, Any]:
#         """Analyze social media component (10% weight)"""
#         prompt = """Analyze social media data and provide a score from 0-10.

# Social media is inherently negative-biased. Score conservatively.

# Scoring Criteria:
# - 8.0-10.0: Positive mentions or minimal negative presence
# - 6.0-7.9: Normal negative bias, no extreme patterns
# - 4.0-5.9: Some concerning patterns
# - 2.0-3.9: Widespread negative patterns
# - 0-1.9: Extreme negative patterns

# Return JSON: {"social_media_score": 6.5, "confidence_level": "Medium", "key_factors": ["factor1", "factor2"]}"""
        
#         data = {
#             # "twitter_mentions": len(twitter_data.get("mentions", [])),
#             # "twitter_own_tweets": len(twitter_data.get("brand_own", [])),
#             "reddit_posts": len(reddit_reviews)
#         }
        
    def analyze_social_media(self, reddit_reviews: List[Dict]) -> Dict[str, Any]:
        """Analyze social media component (10% weight)"""
        # Handle None or empty reddit_reviews
        if not reddit_reviews:
            reddit_reviews = []
            
        prompt = """You are a Social Media Pattern Specialist. Identify significant patterns in social media mentions.

CRITICAL: Social media is inherently negative-biased. Only flag serious, widespread issues.

Scoring Criteria:
- 8.0-10.0: Rare positive mentions or neutral/minimal presence
- 6.0-7.9: Normal negative bias, no extreme patterns
- 4.0-5.9: Concerning patterns but not extreme
- 2.0-3.9: Widespread negative patterns
- 0-1.9: Extreme negative patterns, "avoid this brand" sentiment

Return JSON format:
{
  "social_media_score": 6.5,
  "confidence_level": "Medium",
  "key_factors": [
    "Moderate social media presence with typical negative bias",
    "Some complaints but no extreme widespread issues"
  ],
  "bias_warning": "Social media weighted minimally due to inherent negativity bias"
}"""
        
        social_data = {"reddit_reviews": reddit_reviews, "reddit_count": len(reddit_reviews)}
        return self._call_component_analyzer(prompt, social_data)
    
    def analyze_customer_support(self, google_reviews: List[Dict], reddit_reviews: List[Dict]) -> Dict[str, Any]:
        """Analyze customer support component (10% weight)"""
        prompt = f"""Analyze customer support quality from available review data and provide a score from 0-10.
review data = {google_reviews: {google_reviews}, reddit_reviews: {reddit_reviews}}
Scoring Criteria:
- 8.0-10.0: Few/no support complaints, evidence of good service
- 6.0-7.9: Some complaints but not overwhelming
- 4.0-5.9: Multiple support complaints
- 0-3.9: Widespread support complaints

Return JSON: {"customer_support_score": score calculated, "confidence_level": "Medium", "key_factors": ["factor1", "factor2"]}"""
        
        data = {
            "google_reviews_count": len(google_reviews),
            "reddit_posts_count": len(reddit_reviews),
            "total_data_points": len(google_reviews) + len(reddit_reviews)
        }
        
        return self._call_component_analyzer(prompt, data)




    
#     def analyze_review_sentiment(self, google_reviews: List[Dict], reddit_reviews: List[Dict]) -> Dict[str, Any]:
#         """Analyze review sentiment component (15% weight - increased from 10%)"""
#         prompt = """You are a Review Sentiment Specialist. Analyze review themes and sentiment patterns.

# Scoring Criteria:
# - 8.5-10.0: Outstanding - consistently glowing reviews, net positive ratio >3:1
# - 7.0-8.4: Good - generally positive feedback, ratio 2-3:1
# - 6.0-6.9: Decent - mixed but mostly positive, ratio 1.3-2:1
# - 4.5-5.9: Below Average - more complaints than praise, ratio 0.7-1.3:1
# - 0-4.4: Poor - predominantly negative, ratio <0.7:1

# Return JSON format:
# {
#   "review_sentiment_score": 6.8,
#   "confidence_level": "High",
#   "positive_negative_ratio": 2.1,
#   "key_factors": [
#     "Positive themes dominate with style and comfort praise",
#     "Some durability concerns but manageable",
#     "Overall satisfied customer base"
#   ],
#   "scoring_rationale": "Good score due to 2.1:1 positive/negative ratio"
# }"""
        
#         # Combine review data
#         all_reviews = google_reviews + reddit_reviews
#         sentiment_data = self._prepare_sentiment_data(all_reviews)
#         return self._call_component_analyzer(prompt, sentiment_data)
    
#     # def analyze_social_media(self, twitter_data: Dict, reddit_reviews: List[Dict]) -> Dict[str, Any]:
#     def analyze_social_media(self, reddit_reviews: List[Dict]) -> Dict[str, Any]:
#         """Analyze social media component (10% weight)"""
#         prompt = """You are a Social Media Pattern Specialist. Identify significant patterns in social media mentions.

# CRITICAL: Social media is inherently negative-biased. Only flag serious, widespread issues.

# Scoring Criteria:
# - 8.0-10.0: Rare positive mentions or neutral/minimal presence
# - 6.0-7.9: Normal negative bias, no extreme patterns
# - 4.0-5.9: Concerning patterns but not extreme
# - 2.0-3.9: Widespread negative patterns
# - 0-1.9: Extreme negative patterns, "avoid this brand" sentiment

# Return JSON format:
# {
#   "social_media_score": 6.5,
#   "confidence_level": "Medium",
#   "key_factors": [
#     "Moderate social media presence with typical negative bias",
#     "Some complaints but no extreme widespread issues"
#   ],
#   "bias_warning": "Social media weighted minimally due to inherent negativity bias"
# }"""
        
#         # social_data = {"twitter_data": twitter_data, "reddit_reviews": reddit_reviews}
#         social_data = {"reddit_reviews": reddit_reviews}
#         return self._call_component_analyzer(prompt, social_data)
    
    def analyze_customer_support(self, google_reviews: List[Dict], reddit_reviews: List[Dict]) -> Dict[str, Any]:
        """Analyze customer support component (10% weight)"""
        prompt = """You are a Customer Support Quality Analyst. Evaluate support quality from available data.

Scoring Criteria:
- 8.0-10.0: Few/no support complaints, good marketplace ratings, responsive support
- 6.0-7.9: Some complaints but not overwhelming, average ratings
- 4.0-5.9: Multiple support complaints, poor ratings
- 0-3.9: Widespread support complaints, very poor service

Return JSON format:
{
  "customer_support_score": 7.2,
  "confidence_level": "Medium",
  "key_factors": [
    "Few support-related complaints in reviews",
    "Response time appears reasonable based on mentions"
  ],
  "data_sources": ["Google reviews", "Reddit mentions"]
}"""
        
        all_reviews = google_reviews + reddit_reviews
        support_data = self._prepare_support_data(all_reviews)
        return self._call_component_analyzer(prompt, support_data)
    
    def calculate_trust_score(self, state: BrandAnalysisState) -> Dict[str, Any]:
        """Calculate final trust score without expert opinion"""
        print("🔢 Calculating component scores...")
        
        # Updated weights (removed expert opinion, redistributed)
        weights = {
            'ratings': 0.55,  # Increased from 40%
            'business_legitimacy': 0.10,  # Increased from 10%
            'review_sentiment': 0.20,  # Increased from 10%
            'social_media': 0.10,  # Same
            'customer_support': 0.05  # Same
        }
        
        # Analyze each component
        component_scores = {}
        
        print("  Analyzing ratings...")
        component_scores['ratings'] = self.analyze_ratings(state.get("google_reviews", []))
        
        print("  Analyzing business legitimacy...")
        component_scores['business_legitimacy'] = self.analyze_business_legitimacy(state.get("website_trust_data", {}))
        
        print("  Analyzing review sentiment...")
        component_scores['review_sentiment'] = self.analyze_review_sentiment(
            state.get("google_reviews", []), 
            state.get("reddit_reviews", [])
        )
        
        print("  Analyzing social media...")
        component_scores['social_media'] = self.analyze_social_media(
            # state.get("twitter_data", {}),
            state.get("reddit_reviews", [])
        )
        
        print("  Analyzing customer support...")
        component_scores['customer_support'] = self.analyze_customer_support(
            state.get("google_reviews", []),
            state.get("reddit_reviews", [])
        )
        
        # Calculate final score
        return self._calculate_final_score(component_scores, weights)
    
    def _calculate_final_score(self, component_scores: Dict, weights: Dict) -> Dict[str, Any]:
        """Calculate weighted final score"""
        scores = {}
        
        # Extract scores with error handling
        for component, weight in weights.items():
            component_result = component_scores.get(component, {})
            
            if 'error' in component_result:
                scores[component] = 5.0
            else:
                # Try to find the score - handle both naming conventions
                score_key = f"{component}_score"
                if score_key in component_result:
                    scores[component] = max(0.0, min(10.0, float(component_result[score_key])))
                elif 'score' in component_result:
                    scores[component] = max(0.0, min(10.0, float(component_result['score'])))
                else:
                    scores[component] = 5.0
        
        # Calculate weighted average
        final_score = sum(scores[component] * weights[component] for component in weights.keys())
        
        def interpret_score(score):
            if score >= 8.5: return "Excellent - Strong buy confidence"
            elif score >= 7.0: return "Good - Generally trustworthy"
            elif score >= 5.5: return "Average - Proceed with research"
            elif score >= 4.0: return "Below Average - Significant concerns"
            else: return "Poor - High risk, consider alternatives"
        
        return {
            "final_score": round(final_score, 1),
            "component_breakdown": {
                component: {
                    "score": scores[component],
                    "weight": f"{int(weights[component]*100)}%",
                    "contribution": round(scores[component] * weights[component], 2)
                }
                for component in weights.keys()
            },
            "score_interpretation": interpret_score(final_score),
            "component_results": component_scores
        }
    
    def _prepare_ratings_data(self, google_reviews: List[Dict]) -> Dict[str, Any]:
        """Prepare ratings data for analysis"""
        if not google_reviews:
            return {"total_reviews": 0, "average_rating": 0, "message": "No Google reviews data available"}
        
        # Extract ratings information
        total_reviews = 0
        total_rating = 0
        rating_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        
        for product_data in google_reviews:
            if isinstance(product_data, dict) and "overall_rating" in product_data:
                overall = product_data["overall_rating"]
                if overall and "total_reviews" in overall:
                    total_reviews += overall.get("total_reviews", 0)
                    if "average_rating" in overall:
                        total_rating += overall.get("average_rating", 0)
        
        return {
            "total_reviews": total_reviews,
            "average_rating": total_rating / len(google_reviews) if google_reviews else 0,
            "products_analyzed": len(google_reviews)
        }
    
    def _prepare_sentiment_data(self, all_reviews: List[Dict]) -> Dict[str, Any]:
        """Prepare sentiment data for analysis"""
        if not all_reviews:
            return {"message": "No reviews available for sentiment analysis"}
        
        # Basic sentiment preparation - you can enhance this
        return {
            "total_reviews_analyzed": len(all_reviews),
            "data_sources": ["Google reviews", "Reddit reviews"],
            "message": "Review content available for sentiment analysis"
        }
    
    def _prepare_support_data(self, all_reviews: List[Dict]) -> Dict[str, Any]:
        """Prepare customer support data for analysis"""
        return {
            "total_reviews_analyzed": len(all_reviews),
            "data_sources": ["Google reviews", "Reddit reviews"],
            "message": "Support mentions available for analysis"
        }


class ReportGenerator:
    """Generate comprehensive analysis reports"""
    
    def __init__(self):
        pass
    
    def generate_comprehensive_report(self, state: BrandAnalysisState) -> Dict[str, Any]:
            """Generate a comprehensive analysis report with all component scores"""
            
            trust_score = state.get("trust_score", {})
            final_score = trust_score.get("final_score", 0.0)
            component_breakdown = trust_score.get("component_breakdown", {})
            component_results = trust_score.get("component_results", {})
            
            # Create detailed summary with all scores
            summary = {
                "brand_name": state["brand_name"],
                "overall_score": final_score,
                "recommendation": trust_score.get("score_interpretation", "Unable to determine"),
                "data_sources_analyzed": {
                    "google_reviews": len(state.get("google_reviews", [])),
                    "reddit_reviews": len(state.get("reddit_reviews", [])),
                    # "twitter_mentions": bool(state.get("twitter_data", {})),
                    "website_analysis": bool(state.get("website_trust_data", {}))
                },
                # ADD: Component scores breakdown (this is what was missing!)
                "component_scores": {
                    component_name.replace('_', ' ').title(): {
                        "score": details.get("score", 0),
                        "weight": details.get("weight", "0%"),
                        "contribution": details.get("contribution", 0)
                    }
                    for component_name, details in component_breakdown.items()
                },
                # ADD: Detailed component analysis results
                "detailed_component_analysis": {
                    "ratings": {
                        "score": component_results.get("ratings", {}).get("ratings_score", 0),
                        "confidence": component_results.get("ratings", {}).get("confidence_level", "Unknown"),
                        "key_factors": component_results.get("ratings", {}).get("key_factors", []),
                        "weight": "55%"
                    },
                    "business_legitimacy": {
                        "score": component_results.get("business_legitimacy", {}).get("business_legitimacy_score", 0),
                        "confidence": component_results.get("business_legitimacy", {}).get("confidence_level", "Unknown"),
                        "key_factors": component_results.get("business_legitimacy", {}).get("key_factors", []),
                        "weight": "10%"
                    },
                    "review_sentiment": {
                        "score": component_results.get("review_sentiment", {}).get("review_sentiment_score", 0),
                        "confidence": component_results.get("review_sentiment", {}).get("confidence_level", "Unknown"),
                        "key_factors": component_results.get("review_sentiment", {}).get("key_factors", []),
                        "weight": "20%"
                    },
                    "social_media": {
                        "score": component_results.get("social_media", {}).get("social_media_score", 0),
                        "confidence": component_results.get("social_media", {}).get("confidence_level", "Unknown"),
                        "key_factors": component_results.get("social_media", {}).get("key_factors", []),
                        "weight": "10%"
                    },
                    "customer_support": {
                        "score": component_results.get("customer_support", {}).get("customer_support_score", 0),
                        "confidence": component_results.get("customer_support", {}).get("confidence_level", "Unknown"),
                        "key_factors": component_results.get("customer_support", {}).get("key_factors", []),
                        "weight": "5%"
                    }
                },
                "key_strengths": [],
                "areas_of_concern": [],
                "data_collection_status": state.get("collection_status", {}),
                # ADD: Complete trust score data for debugging
                "trust_score_details": trust_score
            }
            
            # Identify strengths and concerns based on component scores
            for component, details in component_breakdown.items():
                score = details.get("score", 0)
                weight = details.get("weight", "0%")
                component_display = component.replace('_', ' ').title()
                
                if score >= 7.5:
                    summary["key_strengths"].append(f"{component_display}: {score}/10 ({weight})")
                elif score < 5.5:
                    summary["areas_of_concern"].append(f"{component_display}: {score}/10 ({weight})")
            
            return summary


def main():
    """Main function to run brand analysis"""
    print("🎯 Brand Trust Analysis System")
    print("=" * 50)
    
    # Get user input
    brand_name = input("Enter brand name: ").strip()
    twitter_handle = input("Enter Twitter handle (optional, press Enter to skip): ").strip() or None
    website = input("Enter website URL (optional, press Enter to skip): ").strip() or None
    
    if not brand_name:
        print("❌ Brand name is required!")
        return
    
    # Initialize analyzer
    analyzer = BrandAnalyzer()
    
    # Run analysis
    print(f"\n🚀 Starting comprehensive analysis for: {brand_name}")
    start_time = time.time()
    
    result = analyzer.analyze_brand(brand_name, twitter_handle, website)
    
    end_time = time.time()
    duration = end_time - start_time
    
    # Display results
    print("\n" + "=" * 60)
    print("📊 ANALYSIS COMPLETE")
    print("=" * 60)
    
    if "error" in result:
        print(f"❌ Analysis failed: {result['error']}")
        return
    
    trust_score = result.get("trust_score", {})
    final_report = result.get("final_report", {})
    
    print(f"🏷️  Brand: {brand_name}")
    print(f"⭐ Overall Score: {trust_score.get('final_score', 'N/A')}/10")
    print(f"📝 Recommendation: {trust_score.get('score_interpretation', 'N/A')}")
    print(f"⏱️  Analysis Duration: {duration:.1f} seconds")
    
    # Component breakdown
    component_breakdown = trust_score.get("component_breakdown", {})
    if component_breakdown:
        print("\n📊 Component Scores:")
        for component, details in component_breakdown.items():
            print(f"  • {component.replace('_', ' ').title()}: {details.get('score', 'N/A')}/10 ({details.get('weight', 'N/A')})")
    
    # Data collection status
    collection_status = result.get("collection_status", {})
    if collection_status:
        print("\n📈 Data Collection Status:")
        for source, status in collection_status.items():
            status_emoji = "✅" if status == "completed" else "❌"
            print(f"  {status_emoji} {source.replace('_', ' ').title()}: {status}")
    
    print(f"\n💾 Detailed results saved to: {brand_name.lower().replace(' ', '_')}_analysis.json")


if __name__ == "__main__":
    main()
