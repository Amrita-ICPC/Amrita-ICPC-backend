"""
Standalone question definitions for two additional DSA patterns: Dynamic
Programming (0/1 Knapsack) and Recursion/Backtracking (generate all subsets).
Written to match the exact schema of `scripts/seed_question_bank.py`'s
`QUESTIONS` list entries (same `tc()` helper contract, same dict shape) so
this list can be spliced directly into that file's `QUESTIONS` list by a
later integration pass.

Both solution_code + driver_code combinations (Python, C++, Java) were
verified against the live Judge0 instance for every testcase before being
embedded here, mirroring exactly how the platform concatenates
`source_code + "\\n\\n" + driver_code` at judge time (see
app/service/code_execution_service.py and
app/api/routes/v1/students/contest_questions.py).

Note (Java-specific constraint, same as scripts/seed_question_bank.py):
driver_code for Java never uses an `import` statement, since it is appended
*after* the student's `class Solution { ... }` and Java requires all
imports to precede any type declaration in the file. Fully-qualified names
(e.g. `java.util.Scanner`, `java.util.ArrayList`) are used instead.

New tags introduced by this file (not present in scripts/seed_question_bank.py's
ALL_TAGS): "Dynamic Programming", "Recursion", "Backtracking".
"""

from app.utils.enums import QuestionDifficulty


def tc(input_, output, is_hidden, weight=1):
    return {"input": input_, "output": output, "is_hidden": is_hidden, "weight": weight}


QUESTIONS = [
    # ------------------------------------------------------------------
    # 1. MEDIUM - Dynamic Programming - 0/1 Knapsack
    # ------------------------------------------------------------------
    {
        "title": "0/1 Knapsack - Maximum Value",
        "difficulty": QuestionDifficulty.MEDIUM,
        "time_limit_ms": 1000,
        "memory_limit_mb": 256,
        "tags": ["Dynamic Programming", "Arrays"],
        "text": """You are given `n` items. The `i`-th item has weight `weight[i]` and value `value[i]`. You also have a knapsack with a maximum weight capacity `W`.

Choose a subset of the items (each item may be taken at most once - hence "0/1") such that the total weight of the chosen items does not exceed `W`, and the total value of the chosen items is maximized.

Your task is to output the maximum total value achievable. Solve it using dynamic programming (a 1-D or 2-D DP over capacity is expected; brute force over all 2^n subsets will exceed the time limit for larger inputs).

### Input Format
- Line 1: two space-separated integers `n` and `W` - the number of items and the knapsack capacity.
- Line 2: `n` space-separated integers - the weights of the items, `weight[0] weight[1] ... weight[n-1]`. (Empty/omitted if n = 0.)
- Line 3: `n` space-separated integers - the values of the items, `value[0] value[1] ... value[n-1]`. (Empty/omitted if n = 0.)

### Output Format
Print a single integer: the maximum total value obtainable without exceeding capacity `W`.

### Constraints
- 0 <= n <= 100
- 0 <= W <= 1000
- 0 <= weight[i] <= 1000
- 0 <= value[i] <= 10^4
- If n = 0 (no items available), the answer is 0.

### Example
Input:
```
4 7
1 3 4 5
1 4 5 7
```
Output:
```
9
```
Explanation: Taking the items with weight 3 (value 4) and weight 4 (value 5) uses 3 + 4 = 7 <= 7 capacity for a total value of 4 + 5 = 9, which is optimal.
""",
        "testcases": [
            tc("4 7\n1 3 4 5\n1 4 5 7", "9", False),
            tc("3 50\n10 10 10\n60 60 60", "180", False),
            tc("3 5\n10 20 30\n60 100 120", "0", True),
            tc("0 10\n\n", "0", True),
            tc("1 1\n1\n10", "10", True),
            tc(
                "10 50\n2 3 4 5 9 7 1 6 8 10\n3 4 5 8 10 6 2 7 9 11",
                "59",
                True,
            ),
        ],
        "templates": {
            "python": {
                "starter": """class Solution:
    def knapsack(self, n, W, weights, values):
        # weights and values are length-n lists; W is the capacity.
        # Return the maximum total value achievable without exceeding W,
        # using each item at most once.
        # TODO: implement using dynamic programming
        pass
""",
                "driver": """import sys

def main():
    data = sys.stdin.read().split()
    idx = 0
    n = int(data[idx]); idx += 1
    W = int(data[idx]); idx += 1
    weights = [int(data[idx + i]) for i in range(n)]
    idx += n
    values = [int(data[idx + i]) for i in range(n)]
    idx += n
    sol = Solution()
    result = sol.knapsack(n, W, weights, values)
    print(result)

if __name__ == "__main__":
    main()
""",
                "solution": """class Solution:
    def knapsack(self, n, W, weights, values):
        dp = [0] * (W + 1)
        for i in range(n):
            w = weights[i]
            v = values[i]
            for cap in range(W, w - 1, -1):
                if dp[cap - w] + v > dp[cap]:
                    dp[cap] = dp[cap - w] + v
        return dp[W]
""",
            },
            "cpp": {
                "starter": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    int knapsack(int n, int W, vector<int>& weights, vector<int>& values) {
        // Return the maximum total value achievable without exceeding W,
        // using each item at most once.
        // TODO: implement using dynamic programming
        return 0;
    }
};
""",
                "driver": """int main() {
    int n, W;
    cin >> n >> W;
    vector<int> weights(n), values(n);
    for (int i = 0; i < n; i++) cin >> weights[i];
    for (int i = 0; i < n; i++) cin >> values[i];
    Solution sol;
    int result = sol.knapsack(n, W, weights, values);
    cout << result << endl;
    return 0;
}
""",
                "solution": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    int knapsack(int n, int W, vector<int>& weights, vector<int>& values) {
        vector<int> dp(W + 1, 0);
        for (int i = 0; i < n; i++) {
            int w = weights[i], v = values[i];
            for (int cap = W; cap >= w; cap--) {
                dp[cap] = max(dp[cap], dp[cap - w] + v);
            }
        }
        return dp[W];
    }
};
""",
            },
            "java": {
                "starter": """class Solution {
    public int knapsack(int n, int W, int[] weights, int[] values) {
        // Return the maximum total value achievable without exceeding W,
        // using each item at most once.
        // TODO: implement using dynamic programming
        return 0;
    }
}
""",
                "driver": """public class Main {
    public static void main(String[] args) {
        java.util.Scanner sc = new java.util.Scanner(System.in);
        int n = sc.nextInt();
        int W = sc.nextInt();
        int[] weights = new int[n];
        for (int i = 0; i < n; i++) weights[i] = sc.nextInt();
        int[] values = new int[n];
        for (int i = 0; i < n; i++) values[i] = sc.nextInt();
        Solution sol = new Solution();
        int result = sol.knapsack(n, W, weights, values);
        System.out.println(result);
    }
}
""",
                "solution": """class Solution {
    public int knapsack(int n, int W, int[] weights, int[] values) {
        int[] dp = new int[W + 1];
        for (int i = 0; i < n; i++) {
            int w = weights[i], v = values[i];
            for (int cap = W; cap >= w; cap--) {
                dp[cap] = Math.max(dp[cap], dp[cap - w] + v);
            }
        }
        return dp[W];
    }
}
""",
            },
        },
    },
    # ------------------------------------------------------------------
    # 2. EASY - Recursion/Backtracking - Generate All Subsets (Power Set)
    # ------------------------------------------------------------------
    {
        "title": "Generate All Subsets (Power Set) via Recursive Backtracking",
        "difficulty": QuestionDifficulty.EASY,
        "time_limit_ms": 1000,
        "memory_limit_mb": 256,
        "tags": ["Recursion", "Backtracking", "Arrays"],
        "text": """You are given an array `arr` of `n` integers (values may repeat - each element is treated as a distinct position, so two elements with the same value are still included/excluded independently).

Generate every subset of `arr` (there are exactly 2^n of them, including the empty subset) using EXACTLY the following recursive backtracking procedure, so the output order is fully deterministic:

```
current = []
def recurse(index):
    if index == n:
        output current            # print elements of current, space-separated
        return                    # (an empty line if current is empty)
    current.append(arr[index])
    recurse(index + 1)            # branch 1: include arr[index]
    current.pop()
    recurse(index + 1)            # branch 2: exclude arr[index]

recurse(0)
```

In other words: at every index, first fully explore the branch where the current element IS included (printing every subset that contains it), then explore the branch where it is excluded.

### Input Format
- Line 1: a single integer `n`.
- Line 2: `n` space-separated integers, `arr[0] arr[1] ... arr[n-1]`. (Empty/omitted if n = 0.)

### Output Format
Print exactly 2^n lines, one per subset, in the order produced by the recursive procedure above. Each line contains the elements of that subset in their original array order, separated by single spaces. Print an empty line for the empty subset (this will be the very last line printed).

### Constraints
- 0 <= n <= 12
- -10^4 <= arr[i] <= 10^4

### Example
Input:
```
3
1 2 3
```
Output:
```
1 2 3
1 2
1 3
1
2 3
2
3

```
Explanation: Following the recursion: include 1, include 2, include 3 gives {1,2,3} first; backtracking to exclude 3 gives {1,2}; excluding 2 (but including 3) gives {1,3}; excluding both 2 and 3 gives {1}. The same pattern then repeats for the branch that excludes 1: {2,3}, {2}, {3}, and finally the empty subset {} (printed as a blank line, last).
""",
        "testcases": [
            tc("3\n1 2 3", "1 2 3\n1 2\n1 3\n1\n2 3\n2\n3", False),
            tc("1\n7", "7", False),
            tc("0\n", "", True),
            tc("2\n5 5", "5 5\n5\n5", True),
            tc("3\n-1 2 -3", "-1 2 -3\n-1 2\n-1 -3\n-1\n2 -3\n2\n-3", True),
            tc(
                "5\n10 20 30 40 50",
                "10 20 30 40 50\n10 20 30 40\n10 20 30 50\n10 20 30\n"
                "10 20 40 50\n10 20 40\n10 20 50\n10 20\n"
                "10 30 40 50\n10 30 40\n10 30 50\n10 30\n"
                "10 40 50\n10 40\n10 50\n10\n"
                "20 30 40 50\n20 30 40\n20 30 50\n20 30\n"
                "20 40 50\n20 40\n20 50\n20\n"
                "30 40 50\n30 40\n30 50\n30\n"
                "40 50\n40\n50",
                True,
            ),
        ],
        "templates": {
            "python": {
                "starter": """class Solution:
    def generateSubsets(self, arr):
        # Return a list of subsets (each a list of ints), generated by:
        # for each index, first recurse *including* arr[index], then
        # recurse *excluding* it, appending the current subset to the
        # result whenever index reaches len(arr).
        # TODO: implement using recursion/backtracking
        pass
""",
                "driver": """import sys

def main():
    data = sys.stdin.read().split()
    idx = 0
    n = int(data[idx]); idx += 1
    arr = [int(data[idx + i]) for i in range(n)]
    idx += n
    sol = Solution()
    subsets = sol.generateSubsets(arr)
    lines = [" ".join(map(str, s)) for s in subsets]
    print("\\n".join(lines))

if __name__ == "__main__":
    main()
""",
                "solution": """class Solution:
    def generateSubsets(self, arr):
        n = len(arr)
        result = []
        current = []

        def recurse(index):
            if index == n:
                result.append(list(current))
                return
            current.append(arr[index])
            recurse(index + 1)
            current.pop()
            recurse(index + 1)

        recurse(0)
        return result
""",
            },
            "cpp": {
                "starter": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    vector<vector<int>> generateSubsets(vector<int>& arr) {
        // Return every subset of arr, generated by: for each index, first
        // recurse *including* arr[index], then recurse *excluding* it,
        // recording the current subset whenever index reaches arr.size().
        // TODO: implement using recursion/backtracking
        return {};
    }
};
""",
                "driver": """int main() {
    int n;
    cin >> n;
    vector<int> arr(n);
    for (int i = 0; i < n; i++) cin >> arr[i];
    Solution sol;
    vector<vector<int>> subsets = sol.generateSubsets(arr);
    for (auto& s : subsets) {
        for (size_t i = 0; i < s.size(); i++) {
            if (i > 0) cout << " ";
            cout << s[i];
        }
        cout << "\\n";
    }
    return 0;
}
""",
                "solution": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    vector<vector<int>> generateSubsets(vector<int>& arr) {
        int n = (int)arr.size();
        vector<vector<int>> result;
        vector<int> current;
        function<void(int)> recurse = [&](int index) {
            if (index == n) {
                result.push_back(current);
                return;
            }
            current.push_back(arr[index]);
            recurse(index + 1);
            current.pop_back();
            recurse(index + 1);
        };
        recurse(0);
        return result;
    }
};
""",
            },
            "java": {
                "starter": """class Solution {
    public java.util.List<java.util.List<Integer>> generateSubsets(int[] arr) {
        // Return every subset of arr, generated by: for each index, first
        // recurse *including* arr[index], then recurse *excluding* it,
        // recording the current subset whenever index reaches arr.length.
        // TODO: implement using recursion/backtracking
        return new java.util.ArrayList<>();
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
        java.util.List<java.util.List<Integer>> subsets = sol.generateSubsets(arr);
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < subsets.size(); i++) {
            java.util.List<Integer> s = subsets.get(i);
            for (int j = 0; j < s.size(); j++) {
                if (j > 0) sb.append(" ");
                sb.append(s.get(j));
            }
            if (i + 1 < subsets.size()) sb.append("\\n");
        }
        System.out.println(sb.toString());
    }
}
""",
                "solution": """class Solution {
    public java.util.List<java.util.List<Integer>> generateSubsets(int[] arr) {
        java.util.List<java.util.List<Integer>> result = new java.util.ArrayList<>();
        java.util.List<Integer> current = new java.util.ArrayList<>();
        generateHelper(arr, 0, current, result);
        return result;
    }

    private void generateHelper(int[] arr, int index, java.util.List<Integer> current,
                                 java.util.List<java.util.List<Integer>> result) {
        if (index == arr.length) {
            result.add(new java.util.ArrayList<>(current));
            return;
        }
        current.add(arr[index]);
        generateHelper(arr, index + 1, current, result);
        current.remove(current.size() - 1);
        generateHelper(arr, index + 1, current, result);
    }
}
""",
            },
        },
    },
]
