"""
Seed script for a curated DSA "question bank" for the admin side.

Creates a single Bank containing 13 hand-written, fully verified questions
covering contest-level DSA patterns: two pointers, fixed/variable sliding
window, prefix-sum subarray counting, sort + two-pointer triplet search,
dynamic programming (0/1 knapsack), recursion/backtracking (subsets),
stack (bracket matching), queue (sliding window maximum), graph traversal
(BFS/DFS connected components), and binary search (first/last occurrence).
The dynamic-programming/recursion, stack/queue, and graph/binary-search
questions are authored in loadtest/question_bank_data/ and spliced into
QUESTIONS below - see those files' module docstrings for their own
verification details.

Each question ships with:
  - a full problem statement (question_text)
  - visible + hidden testcases (some deliberately tricky: negatives, zeros,
    duplicates, empty strings, large magnitudes)
  - starter_code / driver_code / solution_code templates for Python, C++,
    and Java

All solution_code + driver_code combinations were compiled and executed
locally (CPython 3, GCC 13, and a JDK 17 container) against every testcase
before being embedded here, mirroring exactly how the platform concatenates
`source_code + "\\n\\n" + driver_code` at judge time (see
worker/evaluation_service.py and app/service/code_execution_service.py).

Note (Java-specific constraint): driver_code for Java never uses an
`import` statement, since it is appended *after* the student's `class
Solution { ... }` and Java requires all imports to precede any type
declaration in the file. Fully-qualified names (e.g. `java.util.Scanner`)
are used instead.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clients.database import SessionLocal
from app.models.bank import Bank, BankQuestion
from app.models.language import Language
from app.models.question import Question, QuestionLanguage, QuestionTemplate, TestCase
from app.models.tag import QuestionTag, Tag
from app.models.user import User
from app.utils.enums import QuestionDifficulty, UserRole
from loadtest.question_bank_data.dp_recursion_questions import (
    QUESTIONS as DP_RECURSION_QUESTIONS,
)
from loadtest.question_bank_data.graph_binary_search_questions import (
    QUESTIONS as GRAPH_BINARY_SEARCH_QUESTIONS,
)
from loadtest.question_bank_data.stack_queue_questions import (
    QUESTIONS as STACK_QUEUE_QUESTIONS,
)

BANK_NAME = "DSA Patterns - Curated Question Bank"

# `Language.id` IS the Judge0 language id directly (see app/models/language.py:
# "use judge0 id directly"). These three ids are verified against the live
# Judge0 deployment's /languages endpoint - if get_or_create_languages let the
# database autoincrement Language.id instead (the previous bug here), every
# submission would silently use whatever language Judge0's autoincremented id
# happens to map to instead of the one the student picked.
LANGUAGE_DEFS = [
    {
        "id": 71,
        "slug": "python",
        "name": "Python (3.8.1)",
        "file_extension": ".py",
        "monaco_language": "python",
    },
    {
        "id": 54,
        "slug": "cpp",
        "name": "C++ (GCC 9.2.0)",
        "file_extension": ".cpp",
        "monaco_language": "cpp",
    },
    {
        "id": 62,
        "slug": "java",
        "name": "Java (OpenJDK 13.0.1)",
        "file_extension": ".java",
        "monaco_language": "java",
    },
]

ALL_TAGS = [
    "Arrays",
    "Strings",
    "Two Pointers",
    "Sliding Window",
    "Subarray",
    "Prefix Sum",
    "Hashing",
    "Sorting",
    "Greedy",
    # Added alongside dp_recursion/stack_queue/graph_binary_search_questions.py
    "Dynamic Programming",
    "Recursion",
    "Backtracking",
    "Stack",
    "Queue",
    "Graph",
    "BFS",
    "DFS",
    "Binary Search",
]


def tc(input_, output, is_hidden, weight=1):
    return {"input": input_, "output": output, "is_hidden": is_hidden, "weight": weight}


QUESTIONS = [
    # ------------------------------------------------------------------
    # 1. EASY - Two Pointers
    # ------------------------------------------------------------------
    {
        "title": "Two Sum II - Sorted Array (Two Pointers)",
        "difficulty": QuestionDifficulty.EASY,
        "time_limit_ms": 1000,
        "memory_limit_mb": 256,
        "tags": ["Arrays", "Two Pointers"],
        "text": """You are given a 1-indexed array of integers `arr` that is already sorted in non-decreasing order, and an integer `target`.

Find two distinct indices `i` and `j` (1 <= i < j <= n) such that `arr[i] + arr[j] == target`. It is guaranteed that exactly one such pair exists for every test case.

Your solution should run in O(n) time using the two-pointer technique: start one pointer at the beginning and one at the end of the array, and move them inward based on how the current sum compares to the target.

### Input Format
- Line 1: a single integer `n`, the size of the array.
- Line 2: `n` space-separated integers, the sorted array `arr` (may contain negative numbers).
- Line 3: a single integer `target`.

### Output Format
Print the two 1-indexed positions `i j` (with i < j) separated by a single space.

### Constraints
- 2 <= n <= 10^5
- -10^9 <= arr[i], target <= 10^9
- `arr` is sorted in non-decreasing order.
- Exactly one valid pair exists.

### Example
Input:
```
4
1 2 4 7
6
```
Output:
```
2 3
```
Explanation: arr[2] + arr[3] = 2 + 4 = 6.
""",
        "testcases": [
            tc("4\n1 2 4 7\n6", "2 3", False),
            tc("5\n-4 -1 0 3 10\n9", "2 5", False),
            tc("6\n-6 -5 -3 -1 2 4\n-8", "2 3", True),
            tc("2\n5 10\n15", "1 2", True),
            tc("5\n1 1 2 3 9\n11", "3 5", True),
            tc("5\n-100000 -50 0 4 100000\n0", "1 5", True),
        ],
        "templates": {
            "python": {
                "starter": """class Solution:
    def twoSumSorted(self, arr, target):
        # arr is sorted in ascending order.
        # Return a list [i, j] with 1-based indices such that
        # arr[i-1] + arr[j-1] == target.
        # TODO: implement using the two-pointer technique
        pass
""",
                "driver": """import sys

def main():
    data = sys.stdin.read().split()
    idx = 0
    n = int(data[idx]); idx += 1
    arr = [int(data[idx + i]) for i in range(n)]
    idx += n
    target = int(data[idx])
    sol = Solution()
    result = sol.twoSumSorted(arr, target)
    print(result[0], result[1])

if __name__ == "__main__":
    main()
""",
                "solution": """class Solution:
    def twoSumSorted(self, arr, target):
        left, right = 0, len(arr) - 1
        while left < right:
            s = arr[left] + arr[right]
            if s == target:
                return [left + 1, right + 1]
            elif s < target:
                left += 1
            else:
                right -= 1
        return [-1, -1]
""",
            },
            "cpp": {
                "starter": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    pair<int,int> twoSumSorted(vector<int>& arr, int target) {
        // arr is sorted in ascending order.
        // Return 1-based indices {i, j} such that arr[i-1] + arr[j-1] == target.
        // TODO: implement using the two-pointer technique
        return {-1, -1};
    }
};
""",
                "driver": """int main() {
    int n;
    cin >> n;
    vector<int> arr(n);
    for (int i = 0; i < n; i++) cin >> arr[i];
    int target;
    cin >> target;
    Solution sol;
    pair<int,int> result = sol.twoSumSorted(arr, target);
    cout << result.first << " " << result.second << endl;
    return 0;
}
""",
                "solution": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    pair<int,int> twoSumSorted(vector<int>& arr, int target) {
        int left = 0, right = (int)arr.size() - 1;
        while (left < right) {
            int sum = arr[left] + arr[right];
            if (sum == target) return {left + 1, right + 1};
            else if (sum < target) left++;
            else right--;
        }
        return {-1, -1};
    }
};
""",
            },
            "java": {
                "starter": """class Solution {
    public int[] twoSumSorted(int[] arr, int target) {
        // arr is sorted in ascending order.
        // Return a length-2 array {i, j} with 1-based indices such that
        // arr[i-1] + arr[j-1] == target.
        // TODO: implement using the two-pointer technique
        return new int[]{-1, -1};
    }
}
""",
                "driver": """public class Main {
    public static void main(String[] args) {
        java.util.Scanner sc = new java.util.Scanner(System.in);
        int n = sc.nextInt();
        int[] arr = new int[n];
        for (int i = 0; i < n; i++) arr[i] = sc.nextInt();
        int target = sc.nextInt();
        Solution sol = new Solution();
        int[] result = sol.twoSumSorted(arr, target);
        System.out.println(result[0] + " " + result[1]);
    }
}
""",
                "solution": """class Solution {
    public int[] twoSumSorted(int[] arr, int target) {
        int left = 0, right = arr.length - 1;
        while (left < right) {
            int sum = arr[left] + arr[right];
            if (sum == target) {
                return new int[]{left + 1, right + 1};
            } else if (sum < target) {
                left++;
            } else {
                right--;
            }
        }
        return new int[]{-1, -1};
    }
}
""",
            },
        },
    },
    # ------------------------------------------------------------------
    # 2. EASY - Sliding Window (fixed size)
    # ------------------------------------------------------------------
    {
        "title": "Maximum Sum Subarray of Size K (Sliding Window)",
        "difficulty": QuestionDifficulty.EASY,
        "time_limit_ms": 1000,
        "memory_limit_mb": 256,
        "tags": ["Arrays", "Sliding Window"],
        "text": """Given an array of `n` integers and an integer `k`, find the maximum sum among all contiguous subarrays of size exactly `k`.

Use the sliding window technique: maintain a running sum of the current window of size `k`, and slide it one element at a time by adding the new element and removing the oldest one, in O(1) per step instead of recomputing the sum from scratch.

### Input Format
- Line 1: two integers `n` and `k` separated by a space.
- Line 2: `n` space-separated integers, the array `arr` (can be negative).

### Output Format
Print a single integer: the maximum sum over all contiguous subarrays of size `k`.

### Constraints
- 1 <= k <= n <= 10^5
- -10^6 <= arr[i] <= 10^6

### Example
Input:
```
8 3
2 1 5 1 3 2 1 2
```
Output:
```
9
```
Explanation: The subarray [5, 1, 3] has the maximum sum 9 among all windows of size 3.
""",
        "testcases": [
            tc("8 3\n2 1 5 1 3 2 1 2", "9", False),
            tc("5 2\n-1 -2 -3 -4 -5", "-3", False),
            tc("1 1\n7", "7", True),
            tc("6 6\n1 -2 3 -4 5 -6", "-3", True),
            tc("10 4\n3 -1 4 1 -5 9 2 6 -5 3", "12", True),
            tc("5 3\n1000000 -1000000 1000000 -1000000 1000000", "1000000", True),
        ],
        "templates": {
            "python": {
                "starter": """class Solution:
    def maxSumSubarray(self, arr, k):
        # Return the maximum sum of any contiguous subarray of size k.
        # TODO: implement using the sliding window technique
        pass
""",
                "driver": """import sys

def main():
    data = sys.stdin.read().split()
    idx = 0
    n = int(data[idx]); idx += 1
    k = int(data[idx]); idx += 1
    arr = [int(data[idx + i]) for i in range(n)]
    sol = Solution()
    print(sol.maxSumSubarray(arr, k))

if __name__ == "__main__":
    main()
""",
                "solution": """class Solution:
    def maxSumSubarray(self, arr, k):
        window_sum = sum(arr[:k])
        max_sum = window_sum
        for i in range(k, len(arr)):
            window_sum += arr[i] - arr[i - k]
            max_sum = max(max_sum, window_sum)
        return max_sum
""",
            },
            "cpp": {
                "starter": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    long long maxSumSubarray(vector<int>& arr, int k) {
        // Return the maximum sum of any contiguous subarray of size k.
        // TODO: implement using the sliding window technique
        return 0;
    }
};
""",
                "driver": """int main() {
    int n, k;
    cin >> n >> k;
    vector<int> arr(n);
    for (int i = 0; i < n; i++) cin >> arr[i];
    Solution sol;
    cout << sol.maxSumSubarray(arr, k) << endl;
    return 0;
}
""",
                "solution": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    long long maxSumSubarray(vector<int>& arr, int k) {
        long long windowSum = 0;
        for (int i = 0; i < k; i++) windowSum += arr[i];
        long long maxSum = windowSum;
        for (int i = k; i < (int)arr.size(); i++) {
            windowSum += arr[i] - arr[i - k];
            maxSum = max(maxSum, windowSum);
        }
        return maxSum;
    }
};
""",
            },
            "java": {
                "starter": """class Solution {
    public long maxSumSubarray(int[] arr, int k) {
        // Return the maximum sum of any contiguous subarray of size k.
        // TODO: implement using the sliding window technique
        return 0;
    }
}
""",
                "driver": """public class Main {
    public static void main(String[] args) {
        java.util.Scanner sc = new java.util.Scanner(System.in);
        int n = sc.nextInt();
        int k = sc.nextInt();
        int[] arr = new int[n];
        for (int i = 0; i < n; i++) arr[i] = sc.nextInt();
        Solution sol = new Solution();
        System.out.println(sol.maxSumSubarray(arr, k));
    }
}
""",
                "solution": """class Solution {
    public long maxSumSubarray(int[] arr, int k) {
        long windowSum = 0;
        for (int i = 0; i < k; i++) windowSum += arr[i];
        long maxSum = windowSum;
        for (int i = k; i < arr.length; i++) {
            windowSum += arr[i] - arr[i - k];
            maxSum = Math.max(maxSum, windowSum);
        }
        return maxSum;
    }
}
""",
            },
        },
    },
    # ------------------------------------------------------------------
    # 3. EASY - Single-pass greedy (min-so-far)
    # ------------------------------------------------------------------
    {
        "title": "Best Time to Buy and Sell Stock",
        "difficulty": QuestionDifficulty.EASY,
        "time_limit_ms": 1000,
        "memory_limit_mb": 256,
        "tags": ["Arrays", "Greedy"],
        "text": """You are given an array `prices` where `prices[i]` is the price of a stock on day `i` (0-indexed). You may complete at most one transaction: buy on one day and sell on a later day.

Return the maximum profit you can achieve. If no profit is possible, return 0.

This is a single-pass problem: track the minimum price seen so far as you scan left to right, and at each day compute the profit if you sold today against that running minimum.

### Input Format
- Line 1: a single integer `n`, the number of days.
- Line 2: `n` space-separated integers, the prices on each day.

### Output Format
Print a single integer: the maximum achievable profit (0 if none).

### Constraints
- 1 <= n <= 10^5
- 0 <= prices[i] <= 10^6

### Example
Input:
```
6
7 1 5 3 6 4
```
Output:
```
5
```
Explanation: Buy on day 2 (price 1) and sell on day 5 (price 6): profit = 6 - 1 = 5.
""",
        "testcases": [
            tc("6\n7 1 5 3 6 4", "5", False),
            tc("5\n7 6 4 3 1", "0", False),
            tc("1\n100", "0", True),
            tc("8\n3 3 5 0 0 3 1 4", "4", True),
            tc("4\n5 5 5 5", "0", True),
            tc("6\n1 2 3 4 5 6", "5", True),
        ],
        "templates": {
            "python": {
                "starter": """class Solution:
    def maxProfit(self, prices):
        # Return the maximum profit from a single buy followed by a single sell.
        # Return 0 if no profit is possible.
        # TODO: implement using a running minimum price
        pass
""",
                "driver": """import sys

def main():
    data = sys.stdin.read().split()
    idx = 0
    n = int(data[idx]); idx += 1
    prices = [int(data[idx + i]) for i in range(n)]
    sol = Solution()
    print(sol.maxProfit(prices))

if __name__ == "__main__":
    main()
""",
                "solution": """class Solution:
    def maxProfit(self, prices):
        if not prices:
            return 0
        min_price = prices[0]
        max_profit = 0
        for price in prices[1:]:
            if price - min_price > max_profit:
                max_profit = price - min_price
            if price < min_price:
                min_price = price
        return max_profit
""",
            },
            "cpp": {
                "starter": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    int maxProfit(vector<int>& prices) {
        // Return the maximum profit from a single buy followed by a single sell.
        // Return 0 if no profit is possible.
        // TODO: implement using a running minimum price
        return 0;
    }
};
""",
                "driver": """int main() {
    int n;
    cin >> n;
    vector<int> prices(n);
    for (int i = 0; i < n; i++) cin >> prices[i];
    Solution sol;
    cout << sol.maxProfit(prices) << endl;
    return 0;
}
""",
                "solution": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    int maxProfit(vector<int>& prices) {
        if (prices.empty()) return 0;
        int minPrice = prices[0];
        int maxProfit = 0;
        for (size_t i = 1; i < prices.size(); i++) {
            if (prices[i] - minPrice > maxProfit) maxProfit = prices[i] - minPrice;
            if (prices[i] < minPrice) minPrice = prices[i];
        }
        return maxProfit;
    }
};
""",
            },
            "java": {
                "starter": """class Solution {
    public int maxProfit(int[] prices) {
        // Return the maximum profit from a single buy followed by a single sell.
        // Return 0 if no profit is possible.
        // TODO: implement using a running minimum price
        return 0;
    }
}
""",
                "driver": """public class Main {
    public static void main(String[] args) {
        java.util.Scanner sc = new java.util.Scanner(System.in);
        int n = sc.nextInt();
        int[] prices = new int[n];
        for (int i = 0; i < n; i++) prices[i] = sc.nextInt();
        Solution sol = new Solution();
        System.out.println(sol.maxProfit(prices));
    }
}
""",
                "solution": """class Solution {
    public int maxProfit(int[] prices) {
        if (prices.length == 0) return 0;
        int minPrice = prices[0];
        int maxProfit = 0;
        for (int i = 1; i < prices.length; i++) {
            if (prices[i] - minPrice > maxProfit) maxProfit = prices[i] - minPrice;
            if (prices[i] < minPrice) minPrice = prices[i];
        }
        return maxProfit;
    }
}
""",
            },
        },
    },
    # ------------------------------------------------------------------
    # 4. MEDIUM - Sliding Window (variable size)
    # ------------------------------------------------------------------
    {
        "title": "Longest Substring Without Repeating Characters",
        "difficulty": QuestionDifficulty.MEDIUM,
        "time_limit_ms": 2000,
        "memory_limit_mb": 256,
        "tags": ["Strings", "Sliding Window", "Hashing"],
        "text": """Given a string `s`, find the length of the longest substring of `s` that does not contain any repeating characters.

Use the sliding window technique with two pointers: expand the right pointer to include new characters, and whenever a repeated character is found within the current window, shrink from the left until the window is valid again. Track the last-seen index of each character to achieve O(n) time.

### Input Format
A single line containing the string `s`. `s` may be empty (an empty line) and may contain spaces or any printable characters.

### Output Format
Print a single integer: the length of the longest substring without repeating characters.

### Constraints
- 0 <= |s| <= 10^5

### Example
Input:
```
abcabcbb
```
Output:
```
3
```
Explanation: The answer is "abc", with length 3.
""",
        "testcases": [
            tc("abcabcbb", "3", False),
            tc("bbbbb", "1", False),
            tc("pwwkew", "3", True),
            tc("", "0", True),
            tc("tmmzuxt", "5", True),
            tc("ab cba", "4", True),
        ],
        "templates": {
            "python": {
                "starter": """class Solution:
    def lengthOfLongestSubstring(self, s):
        # Return the length of the longest substring of s without repeating characters.
        # TODO: implement using the sliding window technique
        pass
""",
                "driver": """import sys

def main():
    s = sys.stdin.readline()
    s = s.rstrip("\\r\\n")
    sol = Solution()
    print(sol.lengthOfLongestSubstring(s))

if __name__ == "__main__":
    main()
""",
                "solution": """class Solution:
    def lengthOfLongestSubstring(self, s):
        last_seen = {}
        start = 0
        max_len = 0
        for i, ch in enumerate(s):
            if ch in last_seen and last_seen[ch] >= start:
                start = last_seen[ch] + 1
            last_seen[ch] = i
            max_len = max(max_len, i - start + 1)
        return max_len
""",
            },
            "cpp": {
                "starter": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    int lengthOfLongestSubstring(string s) {
        // Return the length of the longest substring of s without repeating characters.
        // TODO: implement using the sliding window technique
        return 0;
    }
};
""",
                "driver": """int main() {
    string s;
    getline(cin, s);
    if (!s.empty() && s.back() == '\\r') s.pop_back();
    Solution sol;
    cout << sol.lengthOfLongestSubstring(s) << endl;
    return 0;
}
""",
                "solution": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    int lengthOfLongestSubstring(string s) {
        unordered_map<char,int> lastSeen;
        int start = 0, maxLen = 0;
        for (int i = 0; i < (int)s.size(); i++) {
            char ch = s[i];
            auto it = lastSeen.find(ch);
            if (it != lastSeen.end() && it->second >= start) {
                start = it->second + 1;
            }
            lastSeen[ch] = i;
            maxLen = max(maxLen, i - start + 1);
        }
        return maxLen;
    }
};
""",
            },
            "java": {
                "starter": """class Solution {
    public int lengthOfLongestSubstring(String s) {
        // Return the length of the longest substring of s without repeating characters.
        // TODO: implement using the sliding window technique
        return 0;
    }
}
""",
                "driver": """public class Main {
    public static void main(String[] args) {
        java.util.Scanner sc = new java.util.Scanner(System.in);
        String s = sc.hasNextLine() ? sc.nextLine() : "";
        Solution sol = new Solution();
        System.out.println(sol.lengthOfLongestSubstring(s));
    }
}
""",
                "solution": """class Solution {
    public int lengthOfLongestSubstring(String s) {
        java.util.Map<Character, Integer> lastSeen = new java.util.HashMap<>();
        int start = 0, maxLen = 0;
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);
            if (lastSeen.containsKey(ch) && lastSeen.get(ch) >= start) {
                start = lastSeen.get(ch) + 1;
            }
            lastSeen.put(ch, i);
            maxLen = Math.max(maxLen, i - start + 1);
        }
        return maxLen;
    }
}
""",
            },
        },
    },
    # ------------------------------------------------------------------
    # 5. MEDIUM - Prefix Sum + HashMap (subarray counting)
    # ------------------------------------------------------------------
    {
        "title": "Subarray Sum Equals K",
        "difficulty": QuestionDifficulty.MEDIUM,
        "time_limit_ms": 2000,
        "memory_limit_mb": 256,
        "tags": ["Arrays", "Subarray", "Prefix Sum", "Hashing"],
        "text": """Given an array of `n` integers (which may include negative numbers and zeros) and an integer `k`, return the total number of contiguous subarrays whose elements sum to exactly `k`.

This problem cannot be solved efficiently with a simple sliding window, because the array may contain negative numbers (the window sum is not monotonic). Instead, use prefix sums: maintain a running prefix sum and a hashmap of how many times each prefix sum value has occurred so far. For each new prefix sum `P`, the number of valid subarrays ending at the current index equals the count of `P - k` seen previously.

### Input Format
- Line 1: two integers `n` and `k` separated by a space.
- Line 2: `n` space-separated integers, the array `arr`.

### Output Format
Print a single integer: the number of contiguous subarrays summing to `k`.

### Constraints
- 1 <= n <= 10^5
- -10^4 <= arr[i], k <= 10^4

### Example
Input:
```
3 2
1 1 1
```
Output:
```
2
```
Explanation: The subarrays [1,1] (indices 1-2) and [1,1] (indices 2-3) both sum to 2.
""",
        "testcases": [
            tc("3 2\n1 1 1", "2", False),
            tc("3 3\n1 2 3", "2", False),
            tc("5 0\n0 0 0 0 0", "15", True),
            tc("5 -3\n-1 -1 -1 1 1", "1", True),
            tc("1 5\n5", "1", True),
            tc("1 0\n7", "0", True),
        ],
        "templates": {
            "python": {
                "starter": """class Solution:
    def subarraySum(self, arr, k):
        # Return the number of contiguous subarrays whose sum equals k.
        # TODO: implement using prefix sums + a hashmap
        pass
""",
                "driver": """import sys

def main():
    data = sys.stdin.read().split()
    idx = 0
    n = int(data[idx]); idx += 1
    k = int(data[idx]); idx += 1
    arr = [int(data[idx + i]) for i in range(n)]
    sol = Solution()
    print(sol.subarraySum(arr, k))

if __name__ == "__main__":
    main()
""",
                "solution": """class Solution:
    def subarraySum(self, arr, k):
        prefix_count = {0: 1}
        prefix_sum = 0
        count = 0
        for num in arr:
            prefix_sum += num
            count += prefix_count.get(prefix_sum - k, 0)
            prefix_count[prefix_sum] = prefix_count.get(prefix_sum, 0) + 1
        return count
""",
            },
            "cpp": {
                "starter": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    int subarraySum(vector<int>& arr, int k) {
        // Return the number of contiguous subarrays whose sum equals k.
        // TODO: implement using prefix sums + a hashmap
        return 0;
    }
};
""",
                "driver": """int main() {
    int n, k;
    cin >> n >> k;
    vector<int> arr(n);
    for (int i = 0; i < n; i++) cin >> arr[i];
    Solution sol;
    cout << sol.subarraySum(arr, k) << endl;
    return 0;
}
""",
                "solution": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    int subarraySum(vector<int>& arr, int k) {
        unordered_map<long long, int> prefixCount;
        prefixCount[0] = 1;
        long long prefixSum = 0;
        int count = 0;
        for (int num : arr) {
            prefixSum += num;
            auto it = prefixCount.find(prefixSum - k);
            if (it != prefixCount.end()) count += it->second;
            prefixCount[prefixSum]++;
        }
        return count;
    }
};
""",
            },
            "java": {
                "starter": """class Solution {
    public int subarraySum(int[] arr, int k) {
        // Return the number of contiguous subarrays whose sum equals k.
        // TODO: implement using prefix sums + a hashmap
        return 0;
    }
}
""",
                "driver": """public class Main {
    public static void main(String[] args) {
        java.util.Scanner sc = new java.util.Scanner(System.in);
        int n = sc.nextInt();
        int k = sc.nextInt();
        int[] arr = new int[n];
        for (int i = 0; i < n; i++) arr[i] = sc.nextInt();
        Solution sol = new Solution();
        System.out.println(sol.subarraySum(arr, k));
    }
}
""",
                "solution": """class Solution {
    public int subarraySum(int[] arr, int k) {
        java.util.Map<Integer, Integer> prefixCount = new java.util.HashMap<>();
        prefixCount.put(0, 1);
        int prefixSum = 0, count = 0;
        for (int num : arr) {
            prefixSum += num;
            count += prefixCount.getOrDefault(prefixSum - k, 0);
            prefixCount.put(prefixSum, prefixCount.getOrDefault(prefixSum, 0) + 1);
        }
        return count;
    }
}
""",
            },
        },
    },
    # ------------------------------------------------------------------
    # 6. MEDIUM - Sort + Two Pointers
    # ------------------------------------------------------------------
    {
        "title": "3Sum - Count Unique Triplets",
        "difficulty": QuestionDifficulty.MEDIUM,
        "time_limit_ms": 2000,
        "memory_limit_mb": 256,
        "tags": ["Arrays", "Two Pointers", "Sorting"],
        "text": """Given an array of `n` integers, count the number of *unique* value-triplets `(a, b, c)` with `a <= b <= c` taken from the array such that `a + b + c == 0`. Two triplets are considered the same if they consist of the same multiset of values, regardless of which array indices produced them.

Approach: sort the array first. Then, for each index `i` (as the smallest element of a candidate triplet), use two pointers - one starting just after `i` and one at the end of the array - moving them inward based on how the running sum compares to 0, while skipping over duplicate values to avoid counting the same triplet more than once.

### Input Format
- Line 1: a single integer `n`.
- Line 2: `n` space-separated integers, the array `arr`.

### Output Format
Print a single integer: the number of unique triplets summing to zero.

### Constraints
- 0 <= n <= 3000
- -10^5 <= arr[i] <= 10^5

### Example
Input:
```
6
-1 0 1 2 -1 -4
```
Output:
```
2
```
Explanation: The unique triplets are (-1, -1, 2) and (-1, 0, 1).
""",
        "testcases": [
            tc("6\n-1 0 1 2 -1 -4", "2", False),
            tc("3\n0 0 0", "1", False),
            tc("3\n1 2 -3", "1", True),
            tc("2\n1 -1", "0", True),
            tc("8\n-2 0 0 2 2 -2 0 0", "2", True),
            tc("6\n1 2 3 4 5 6", "0", True),
        ],
        "templates": {
            "python": {
                "starter": """class Solution:
    def countUniqueTriplets(self, arr):
        # Return the number of unique value-triplets (a, b, c) with a <= b <= c
        # from arr such that a + b + c == 0.
        # TODO: implement using sort + two pointers
        pass
""",
                "driver": """import sys

def main():
    data = sys.stdin.read().split()
    idx = 0
    n = int(data[idx]); idx += 1
    arr = [int(data[idx + i]) for i in range(n)]
    sol = Solution()
    print(sol.countUniqueTriplets(arr))

if __name__ == "__main__":
    main()
""",
                "solution": """class Solution:
    def countUniqueTriplets(self, arr):
        arr = sorted(arr)
        n = len(arr)
        count = 0
        for i in range(n - 2):
            if i > 0 and arr[i] == arr[i - 1]:
                continue
            left, right = i + 1, n - 1
            while left < right:
                total = arr[i] + arr[left] + arr[right]
                if total == 0:
                    count += 1
                    left += 1
                    right -= 1
                    while left < right and arr[left] == arr[left - 1]:
                        left += 1
                    while left < right and arr[right] == arr[right + 1]:
                        right -= 1
                elif total < 0:
                    left += 1
                else:
                    right -= 1
        return count
""",
            },
            "cpp": {
                "starter": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    int countUniqueTriplets(vector<int>& arr) {
        // Return the number of unique value-triplets (a, b, c) with a <= b <= c
        // from arr such that a + b + c == 0.
        // TODO: implement using sort + two pointers
        return 0;
    }
};
""",
                "driver": """int main() {
    int n;
    cin >> n;
    vector<int> arr(n);
    for (int i = 0; i < n; i++) cin >> arr[i];
    Solution sol;
    cout << sol.countUniqueTriplets(arr) << endl;
    return 0;
}
""",
                "solution": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    int countUniqueTriplets(vector<int>& arr) {
        sort(arr.begin(), arr.end());
        int n = arr.size();
        int count = 0;
        for (int i = 0; i < n - 2; i++) {
            if (i > 0 && arr[i] == arr[i - 1]) continue;
            int left = i + 1, right = n - 1;
            while (left < right) {
                long long total = (long long)arr[i] + arr[left] + arr[right];
                if (total == 0) {
                    count++;
                    left++;
                    right--;
                    while (left < right && arr[left] == arr[left - 1]) left++;
                    while (left < right && arr[right] == arr[right + 1]) right--;
                } else if (total < 0) {
                    left++;
                } else {
                    right--;
                }
            }
        }
        return count;
    }
};
""",
            },
            "java": {
                "starter": """class Solution {
    public int countUniqueTriplets(int[] arr) {
        // Return the number of unique value-triplets (a, b, c) with a <= b <= c
        // from arr such that a + b + c == 0.
        // TODO: implement using sort + two pointers
        return 0;
    }
}
""",
                "driver": """public class Main {
    public static void main(String[] args) {
        java.util.Scanner sc = new java.util.Scanner(System.in);
        int n = sc.nextInt();
        int[] arr = new int[n];
        for (int i = 0; i < n; i++) arr[i] = sc.nextInt();
        Solution sol = new Solution();
        System.out.println(sol.countUniqueTriplets(arr));
    }
}
""",
                "solution": """class Solution {
    public int countUniqueTriplets(int[] arr) {
        java.util.Arrays.sort(arr);
        int n = arr.length;
        int count = 0;
        for (int i = 0; i < n - 2; i++) {
            if (i > 0 && arr[i] == arr[i - 1]) continue;
            int left = i + 1, right = n - 1;
            while (left < right) {
                int total = arr[i] + arr[left] + arr[right];
                if (total == 0) {
                    count++;
                    left++;
                    right--;
                    while (left < right && arr[left] == arr[left - 1]) left++;
                    while (left < right && arr[right] == arr[right + 1]) right--;
                } else if (total < 0) {
                    left++;
                } else {
                    right--;
                }
            }
        }
        return count;
    }
}
""",
            },
        },
    },
    # ------------------------------------------------------------------
    # 7. HARD - Sliding Window (variable size, hard)
    # ------------------------------------------------------------------
    {
        "title": "Minimum Window Substring",
        "difficulty": QuestionDifficulty.HARD,
        "time_limit_ms": 3000,
        "memory_limit_mb": 256,
        "tags": ["Strings", "Sliding Window", "Hashing"],
        "text": """Given two strings `s` and `t`, find the length of the smallest substring of `s` that contains every character of `t`, including duplicates (i.e., for each character, the window must contain at least as many occurrences as it appears in `t`). If no such window exists, or if `t` is empty, print 0.

This is the hardest pattern in the sliding window family: a *variable-size* window where you expand the right pointer while the window is invalid, and once all characters of `t` are covered, aggressively shrink from the left to find the smallest valid window before continuing to expand. Maintain a frequency map of characters still "needed" and a count of how many distinct required characters are still missing from the current window.

### Input Format
- Line 1: the string `s`.
- Line 2: the string `t`.
Either string may be empty (an empty line). Both consist of printable non-newline characters.

### Output Format
Print a single integer: the length of the smallest valid window, or 0 if none exists.

### Constraints
- 0 <= |s| <= 10^5
- 0 <= |t| <= |s|

### Example
Input:
```
ADOBECODEBANC
ABC
```
Output:
```
4
```
Explanation: The smallest window containing all of "A", "B", and "C" is "BANC", which has length 4.
""",
        "testcases": [
            tc("ADOBECODEBANC\nABC", "4", False),
            tc("a\na", "1", False),
            tc("a\naa", "0", True),
            tc("ab\nb", "1", True),
            tc("aaflslflsldkalskaaa\naaa", "3", True),
            tc("x\n", "0", True),
        ],
        "templates": {
            "python": {
                "starter": """class Solution:
    def minWindowLength(self, s, t):
        # Return the length of the smallest substring of s that contains
        # every character of t (including duplicates). Return 0 if none
        # exists, or if t is empty.
        # TODO: implement using a variable-size sliding window
        pass
""",
                "driver": """import sys

def main():
    lines = sys.stdin.read().split("\\n")
    s = lines[0] if len(lines) > 0 else ""
    t = lines[1] if len(lines) > 1 else ""
    sol = Solution()
    print(sol.minWindowLength(s, t))

if __name__ == "__main__":
    main()
""",
                "solution": """class Solution:
    def minWindowLength(self, s, t):
        if len(t) == 0:
            return 0
        need = {}
        for ch in t:
            need[ch] = need.get(ch, 0) + 1
        missing = len(t)
        left = 0
        best = len(s) + 1
        for right, ch in enumerate(s):
            if need.get(ch, 0) > 0:
                missing -= 1
            need[ch] = need.get(ch, 0) - 1
            while missing == 0:
                if right - left + 1 < best:
                    best = right - left + 1
                need[s[left]] = need.get(s[left], 0) + 1
                if need[s[left]] > 0:
                    missing += 1
                left += 1
        return 0 if best == len(s) + 1 else best
""",
            },
            "cpp": {
                "starter": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    int minWindowLength(string s, string t) {
        // Return the length of the smallest substring of s that contains
        // every character of t (including duplicates). Return 0 if none
        // exists, or if t is empty.
        // TODO: implement using a variable-size sliding window
        return 0;
    }
};
""",
                "driver": """int main() {
    string s, t;
    getline(cin, s);
    if (!s.empty() && s.back() == '\\r') s.pop_back();
    if (!getline(cin, t)) t = "";
    if (!t.empty() && t.back() == '\\r') t.pop_back();
    Solution sol;
    cout << sol.minWindowLength(s, t) << endl;
    return 0;
}
""",
                "solution": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    int minWindowLength(string s, string t) {
        if (t.empty()) return 0;
        vector<int> need(128, 0);
        for (char c : t) need[(unsigned char)c]++;
        int missing = t.size();
        int left = 0;
        int best = (int)s.size() + 1;
        for (int right = 0; right < (int)s.size(); right++) {
            unsigned char ch = s[right];
            if (need[ch] > 0) missing--;
            need[ch]--;
            while (missing == 0) {
                if (right - left + 1 < best) best = right - left + 1;
                unsigned char lc = s[left];
                need[lc]++;
                if (need[lc] > 0) missing++;
                left++;
            }
        }
        return best == (int)s.size() + 1 ? 0 : best;
    }
};
""",
            },
            "java": {
                "starter": """class Solution {
    public int minWindowLength(String s, String t) {
        // Return the length of the smallest substring of s that contains
        // every character of t (including duplicates). Return 0 if none
        // exists, or if t is empty.
        // TODO: implement using a variable-size sliding window
        return 0;
    }
}
""",
                "driver": """public class Main {
    public static void main(String[] args) throws java.io.IOException {
        java.io.BufferedReader br = new java.io.BufferedReader(new java.io.InputStreamReader(System.in));
        String s = br.readLine();
        String t = br.readLine();
        if (s == null) s = "";
        if (t == null) t = "";
        Solution sol = new Solution();
        System.out.println(sol.minWindowLength(s, t));
    }
}
""",
                "solution": """class Solution {
    public int minWindowLength(String s, String t) {
        if (t.length() == 0) return 0;
        int[] need = new int[128];
        for (int i = 0; i < t.length(); i++) need[t.charAt(i)]++;
        int missing = t.length();
        int left = 0;
        int best = s.length() + 1;
        for (int right = 0; right < s.length(); right++) {
            char ch = s.charAt(right);
            if (need[ch] > 0) missing--;
            need[ch]--;
            while (missing == 0) {
                if (right - left + 1 < best) best = right - left + 1;
                char lc = s.charAt(left);
                need[lc]++;
                if (need[lc] > 0) missing++;
                left++;
            }
        }
        return best == s.length() + 1 ? 0 : best;
    }
}
""",
            },
        },
    },
]

# Additional DSA patterns (Dynamic Programming, Recursion/Backtracking,
# Stack, Queue, Graph, Binary Search), authored + Judge0-verified separately
# in loadtest/question_bank_data/ - see those files' module docstrings for
# verification details.
QUESTIONS = QUESTIONS + DP_RECURSION_QUESTIONS + STACK_QUEUE_QUESTIONS + GRAPH_BINARY_SEARCH_QUESTIONS


async def get_or_create_admin(session: AsyncSession) -> User:
    result = await session.execute(
        select(User).where(User.role == UserRole.admin).limit(1)
    )
    admin = result.scalars().first()
    if not admin:
        admin = User(
            id=uuid.uuid4(),
            user_id="admin_seed",
            name="System Administrator",
            email="admin_seed@example.com",
            phone_no="+1234567890",
            role=UserRole.admin,
            created_at=datetime.now(timezone.utc),
            last_updated=datetime.now(timezone.utc),
        )
        session.add(admin)
        await session.flush()
    return admin


async def get_or_create_languages(session: AsyncSession) -> dict[str, Language]:
    result = await session.execute(select(Language))
    existing = {lang.slug: lang for lang in result.scalars().all()}

    by_slug: dict[str, Language] = {}
    for lang_def in LANGUAGE_DEFS:
        slug = lang_def["slug"]
        if slug in existing:
            by_slug[slug] = existing[slug]
            continue
        lang = Language(
            id=lang_def["id"],
            name=lang_def["name"],
            slug=slug,
            file_extension=lang_def["file_extension"],
            monaco_language=lang_def["monaco_language"],
        )
        session.add(lang)
        by_slug[slug] = lang

    await session.flush()
    return by_slug


async def get_or_create_tags(session: AsyncSession) -> dict[str, Tag]:
    result = await session.execute(select(Tag).where(Tag.name.in_(ALL_TAGS)))
    existing = {tag.name: tag for tag in result.scalars().all()}

    by_name: dict[str, Tag] = {}
    for name in ALL_TAGS:
        if name in existing:
            by_name[name] = existing[name]
            continue
        tag = Tag(id=uuid.uuid4(), name=name)
        session.add(tag)
        by_name[name] = tag

    await session.flush()
    return by_name


async def main():
    async with SessionLocal() as session:
        try:
            print("Setting up admin user...")
            admin = await get_or_create_admin(session)
            print(f"  using admin: {admin.name}")

            print("Setting up languages (python, cpp, java)...")
            languages = await get_or_create_languages(session)
            for slug, lang in languages.items():
                print(f"  {slug} -> language_id={lang.id}")

            print("Setting up tags...")
            tags = await get_or_create_tags(session)
            print(f"  {len(tags)} tags ready")

            existing_bank = await session.execute(
                select(Bank).where(Bank.name == BANK_NAME, Bank.created_by == admin.id)
            )
            if existing_bank.scalars().first():
                print(
                    f"\nBank '{BANK_NAME}' already exists for this admin. "
                    "Skipping to avoid duplicate questions. Delete it first if you "
                    "want to reseed."
                )
                return

            bank = Bank(
                id=uuid.uuid4(),
                name=BANK_NAME,
                description=(
                    "13 hand-picked DSA pattern problems (two pointers, sliding "
                    "window, prefix sum, sorting, dynamic programming, recursion, "
                    "stack, queue, graph traversal, binary search) with verified "
                    "Python/C++/Java solutions and visible + hidden testcases."
                ),
                created_by=admin.id,
            )
            session.add(bank)
            await session.flush()

            now = datetime.now(timezone.utc)
            created_questions = []

            print(f"\nCreating {len(QUESTIONS)} questions...")
            for q_def in QUESTIONS:
                question = Question(
                    id=uuid.uuid4(),
                    title=q_def["title"],
                    question_text=q_def["text"],
                    difficulty=q_def["difficulty"],
                    time_limit_ms=q_def["time_limit_ms"],
                    memory_limit_mb=q_def["memory_limit_mb"],
                    created_by=admin.id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(question)
                await session.flush()

                for slug in ("python", "cpp", "java"):
                    session.add(
                        QuestionLanguage(
                            question_id=question.id,
                            language_id=languages[slug].id,
                        )
                    )

                for order, tc_def in enumerate(q_def["testcases"]):
                    session.add(
                        TestCase(
                            id=uuid.uuid4(),
                            question_id=question.id,
                            input=tc_def["input"],
                            output=tc_def["output"],
                            is_hidden=tc_def["is_hidden"],
                            weight=tc_def["weight"],
                            order=order,
                            created_by=admin.id,
                            created_at=now,
                            updated_at=now,
                        )
                    )

                for slug in ("python", "cpp", "java"):
                    template = q_def["templates"][slug]
                    session.add(
                        QuestionTemplate(
                            id=uuid.uuid4(),
                            question_id=question.id,
                            language_id=languages[slug].id,
                            starter_code=template["starter"],
                            driver_code=template["driver"],
                            solution_code=template["solution"],
                        )
                    )

                for tag_name in q_def["tags"]:
                    session.add(
                        QuestionTag(question_id=question.id, tag_id=tags[tag_name].id)
                    )

                session.add(
                    BankQuestion(
                        id=uuid.uuid4(),
                        bank_id=bank.id,
                        question_id=question.id,
                        created_by=admin.id,
                        created_at=now,
                        updated_at=now,
                    )
                )

                created_questions.append(question)
                print(f"  [{q_def['difficulty'].value:6s}] {q_def['title']}")

            await session.commit()

            print("\nDone.")
            print(f"  Bank: {BANK_NAME} (id={bank.id})")
            print(f"  Questions: {len(created_questions)}")
            print(
                "  Difficulty split: "
                f"{sum(1 for q in QUESTIONS if q['difficulty'] == QuestionDifficulty.EASY)} EASY, "
                f"{sum(1 for q in QUESTIONS if q['difficulty'] == QuestionDifficulty.MEDIUM)} MEDIUM, "
                f"{sum(1 for q in QUESTIONS if q['difficulty'] == QuestionDifficulty.HARD)} HARD"
            )

        except Exception as e:
            await session.rollback()
            print(f"\nError during seeding: {e}")
            import traceback

            traceback.print_exc()
            raise


if __name__ == "__main__":
    asyncio.run(main())
