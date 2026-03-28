# Execution Plan: Recursive Suggested Modals (Flow 1)

Currently, the automation script strictly uses a "Search Page -> Dedicated Listing URL" flow. It iterates over extracted URLs, explicitly navigating (`page.goto`) to every single one. If Internshala displays a "Suggested Internships" popup *after* a successful submission, the script instantly navigates away from it, discarding potentially 1-click apply opportunities.

To support **Flow 1**, we need to switch from a linear iterator to a recursive "DOM Walker" state machine.

### Proposed Architecture Changes

1. **State Injection instead of Hard Navigation**
   - After clicking `Submit` on any application, the script must explicitly wait 3-5 seconds to check if a "Suggested Internships" modal or overlay appears.
   - We must add a new selector to `selectors.yaml` called `suggested_internships_modal` and `modal_apply_now_btn`.

2. **The Recursive Application Loop**
   Instead of sequentially calling `page.goto(url)` for every item from the master array, we use a recursive stack:
   
   ```python
    def apply_recursive(page, depth=0, max_depth=3):
        # Base case to prevent infinite loops from repeating suggestions
        if depth >= max_depth: return
        
        # 1. Look for 'Apply Now' buttons inside the suggested modal
        modal_listings = page.locator(SELECTORS["modal_listing_card"]).all()
        for listing in modal_listings:
            # 2. Click Apply Now
            listing.locator(SELECTORS["modal_apply_now_btn"]).click()
            # 3. Handle Proceed -> Submit flow 
            handle_submit_flow(page)
            # 4. Recursion: Did ANOTHER modal open?
            apply_recursive(page, depth + 1)
   ```

3. **Updating the Parent Iterator**
   - The main script in `apply_one_click_internships` remains the parent loop. 
   - After `submit_btn.click()`, it will immediately call `apply_recursive(page)`. 
   - Once the recursion is exhausted (no more modals match, or depth limit reached), the parent loop resumes and `page.goto(listing_url)` is called for the next *original* search result.

### Self-Healing Considerations
We will need to modify our LLM prompt to understand that expected targets might reside *inside* overlays or modals, not just on the main DOM. We could do this by feeding the agent an accessibility tree instead of raw HTML if the page gets too dynamically complex.

---

# Execution Plan: Robust Data Extraction Healing

Currently, the Self-Healing AI only protects **interactive buttons** (clicks) through the `robust_wait_and_click` wrapper. When the script performs data extraction on the search page (e.g., getting the `company_name` or `listing_url`), it uses unprotected `try/catch` and `query_selector` calls. If these fail, the script silently discards the listing.

### Proposed Architecture Changes

1. **New Wrapper Core: `robust_extract`**
   Create a new helper function alongside `robust_wait_and_click` specifically designed for static data scraping.
   ```python
   def robust_extract(element_handle, selector_key, type="text"):
       # 1. Try standard element_handle.query_selector()
       # 2. If None, check UNHEALABLE_SELECTORS cache to avoid looping failures
       # 3. If not cached, trigger AI: agent.heal_selectors(element_handle.inner_html())
       # 4. If healed, update global SELECTORS, retry extraction. 
       # 5. Else, cache as unhealable and return None.
   ```

2. **Global Failure Propagation & Token Optimization**
   Because extracting `company_name` happens in a `for` loop across 40 individual listings on a single search page, if a selector completely breaks, we absolutely CANNOT trigger the AI 40 times. 
   - **Persistence**: If the AI returns a healed selector for `company_name` on the 1st listing, the script dynamically updates `SELECTORS["company_name"]`. The remaining 39 listings will automatically use the correct selector without ever needing to call the AI again.
   - **Caching**: If the AI returns `FAILURE` for `company_name`, it is added to the `UNHEALABLE_SELECTORS` cache. The script will safely skip extracting this field for the remaining 39 listings, spending $0 on additional AI calls.

3. **Micro-DOM Context Slicing**
   When `robust_extract` fails, it fails *inside a specific listing card*. Rather than sending the entire `page.content()` (100,000 characters) to the AI Agent, we will send only `element.inner_html()` (approx. 2,000 characters). This makes the LLM fast-pass run exponentially quicker, vastly cheaper, and effectively guarantees 100% accuracy because the LLM is only looking at the exact broken card.
