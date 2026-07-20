"""
Standalone question definitions for two additional DSA patterns: Graph
traversal (BFS/DFS) and Binary Search. Written to match the exact schema of
`scripts/seed_question_bank.py`'s `QUESTIONS` list entries (same `tc()`
helper contract, same dict shape) so this list can be spliced directly into
that file's `QUESTIONS` list by a later integration pass.

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
(e.g. `java.util.Scanner`, `java.util.ArrayDeque`) are used instead.

New tags introduced by this file (not present in scripts/seed_question_bank.py's
ALL_TAGS): "Graph", "BFS", "Binary Search".
"""

from app.utils.enums import QuestionDifficulty


def tc(input_, output, is_hidden, weight=1):
    return {"input": input_, "output": output, "is_hidden": is_hidden, "weight": weight}


QUESTIONS = [
    # ------------------------------------------------------------------
    # 1. MEDIUM - Graph (BFS/DFS) - Connected Components
    # ------------------------------------------------------------------
    {
        "title": "Number of Connected Components in an Undirected Graph (BFS/DFS)",
        "difficulty": QuestionDifficulty.MEDIUM,
        "time_limit_ms": 2000,
        "memory_limit_mb": 256,
        "tags": ["Graph", "BFS", "DFS"],
        "text": """You are given an undirected graph with `n` vertices, labeled `1` to `n`, and `m` edges. Some edges may be self-loops (an edge from a vertex to itself) or duplicates of another edge; both must be handled correctly and do not create extra connectivity.

Find the number of connected components in the graph, i.e. the number of maximal groups of vertices such that every vertex in a group is reachable from every other vertex in that group via graph edges. A vertex with no edges at all is its own connected component.

Use a graph traversal (BFS or DFS): build an adjacency list from the edges, then repeatedly start a traversal from any unvisited vertex, mark everything reachable from it as visited, and count how many times you had to start a fresh traversal.

### Input Format
- Line 1: two integers `n` and `m`, the number of vertices and edges.
- Next `m` lines: two integers `u v`, an undirected edge between vertex `u` and vertex `v` (`1 <= u, v <= n`; self-loops with `u == v` and duplicate edges may appear).

### Output Format
Print a single integer: the number of connected components in the graph.

### Constraints
- 1 <= n <= 10^5
- 0 <= m <= 2 * 10^5
- 1 <= u, v <= n

### Example
Input:
```
5 3
1 2
2 3
4 5
```
Output:
```
2
```
Explanation: Vertices {1, 2, 3} form one connected component (via edges 1-2 and 2-3), and vertices {4, 5} form another (via edge 4-5). Total: 2 components.
""",
        "testcases": [
            tc("5 3\n1 2\n2 3\n4 5", "2", False),
            tc("1 0", "1", False),
            tc("4 4\n1 1\n2 2\n3 3\n4 4", "4", True),
            tc("6 5\n1 2\n1 3\n1 2\n4 5\n4 5", "3", True),
            tc(
                "10 9\n1 2\n2 3\n3 4\n4 5\n5 6\n6 7\n7 8\n8 9\n9 10",
                "1",
                True,
            ),
            tc("7 0", "7", True),
        ],
        "templates": {
            "python": {
                "starter": """class Solution:
    def countComponents(self, n, edges):
        # n: number of vertices labeled 1..n
        # edges: list of (u, v) pairs (may include self-loops / duplicates)
        # Return the number of connected components.
        # TODO: implement using BFS or DFS
        pass
""",
                "driver": """import sys
from collections import deque

def main():
    data = sys.stdin.read().split()
    idx = 0
    n = int(data[idx]); idx += 1
    m = int(data[idx]); idx += 1
    edges = []
    for _ in range(m):
        u = int(data[idx]); idx += 1
        v = int(data[idx]); idx += 1
        edges.append((u, v))
    sol = Solution()
    print(sol.countComponents(n, edges))

if __name__ == "__main__":
    main()
""",
                "solution": """from collections import deque

class Solution:
    def countComponents(self, n, edges):
        adj = [[] for _ in range(n + 1)]
        for u, v in edges:
            if u != v:
                adj[u].append(v)
                adj[v].append(u)
        visited = [False] * (n + 1)
        count = 0
        for start in range(1, n + 1):
            if not visited[start]:
                count += 1
                visited[start] = True
                queue = deque([start])
                while queue:
                    node = queue.popleft()
                    for nei in adj[node]:
                        if not visited[nei]:
                            visited[nei] = True
                            queue.append(nei)
        return count
""",
            },
            "cpp": {
                "starter": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    int countComponents(int n, vector<pair<int,int>>& edges) {
        // n: number of vertices labeled 1..n
        // edges: list of (u, v) pairs (may include self-loops / duplicates)
        // Return the number of connected components.
        // TODO: implement using BFS or DFS
        return 0;
    }
};
""",
                "driver": """int main() {
    int n, m;
    cin >> n >> m;
    vector<pair<int,int>> edges(m);
    for (int i = 0; i < m; i++) {
        int u, v;
        cin >> u >> v;
        edges[i] = {u, v};
    }
    Solution sol;
    cout << sol.countComponents(n, edges) << endl;
    return 0;
}
""",
                "solution": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    int countComponents(int n, vector<pair<int,int>>& edges) {
        vector<vector<int>> adj(n + 1);
        for (auto& e : edges) {
            int u = e.first, v = e.second;
            if (u != v) {
                adj[u].push_back(v);
                adj[v].push_back(u);
            }
        }
        vector<bool> visited(n + 1, false);
        int count = 0;
        for (int start = 1; start <= n; start++) {
            if (!visited[start]) {
                count++;
                visited[start] = true;
                queue<int> q;
                q.push(start);
                while (!q.empty()) {
                    int node = q.front();
                    q.pop();
                    for (int nei : adj[node]) {
                        if (!visited[nei]) {
                            visited[nei] = true;
                            q.push(nei);
                        }
                    }
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
    public int countComponents(int n, int[][] edges) {
        // n: number of vertices labeled 1..n
        // edges: array of {u, v} pairs (may include self-loops / duplicates)
        // Return the number of connected components.
        // TODO: implement using BFS or DFS
        return 0;
    }
}
""",
                "driver": """public class Main {
    public static void main(String[] args) {
        java.util.Scanner sc = new java.util.Scanner(System.in);
        int n = sc.nextInt();
        int m = sc.nextInt();
        int[][] edges = new int[m][2];
        for (int i = 0; i < m; i++) {
            edges[i][0] = sc.nextInt();
            edges[i][1] = sc.nextInt();
        }
        Solution sol = new Solution();
        System.out.println(sol.countComponents(n, edges));
    }
}
""",
                "solution": """class Solution {
    public int countComponents(int n, int[][] edges) {
        java.util.List<java.util.List<Integer>> adj = new java.util.ArrayList<>();
        for (int i = 0; i <= n; i++) {
            adj.add(new java.util.ArrayList<>());
        }
        for (int[] e : edges) {
            int u = e[0], v = e[1];
            if (u != v) {
                adj.get(u).add(v);
                adj.get(v).add(u);
            }
        }
        boolean[] visited = new boolean[n + 1];
        int count = 0;
        for (int start = 1; start <= n; start++) {
            if (!visited[start]) {
                count++;
                visited[start] = true;
                java.util.ArrayDeque<Integer> queue = new java.util.ArrayDeque<>();
                queue.add(start);
                while (!queue.isEmpty()) {
                    int node = queue.poll();
                    for (int nei : adj.get(node)) {
                        if (!visited[nei]) {
                            visited[nei] = true;
                            queue.add(nei);
                        }
                    }
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
    # 2. MEDIUM - Binary Search - First and Last Position
    # ------------------------------------------------------------------
    {
        "title": "First and Last Position of a Target in a Sorted Array (Binary Search)",
        "difficulty": QuestionDifficulty.MEDIUM,
        "time_limit_ms": 1000,
        "memory_limit_mb": 256,
        "tags": ["Binary Search"],
        "text": """You are given an array of `n` integers sorted in non-decreasing order, which may contain duplicate values, and an integer `target`.

Find the first (leftmost) and last (rightmost) 1-indexed positions at which `target` appears in the array. If `target` does not appear anywhere in the array, output `-1 -1`.

Your solution should run in O(log n) time using binary search: run two independent binary searches over the sorted array, one biased to keep moving left after finding a match (to locate the leftmost occurrence) and one biased to keep moving right after finding a match (to locate the rightmost occurrence), rather than scanning the array linearly.

### Input Format
- Line 1: a single integer `n`, the size of the array.
- Line 2: `n` space-separated integers, the array `arr`, sorted in non-decreasing order (may contain negatives and duplicates).
- Line 3: a single integer `target`.

### Output Format
Print two integers `first last` (1-indexed positions), separated by a single space. If `target` is not present, print `-1 -1`.

### Constraints
- 1 <= n <= 2 * 10^5
- -10^9 <= arr[i], target <= 10^9
- `arr` is sorted in non-decreasing order.

### Example
Input:
```
6
5 7 7 8 8 10
8
```
Output:
```
4 5
```
Explanation: The value 8 first appears at 1-indexed position 4 and last appears at position 5.
""",
        "testcases": [
            tc("6\n5 7 7 8 8 10\n8", "4 5", False),
            tc("6\n5 7 7 8 8 10\n6", "-1 -1", False),
            tc("1\n5\n5", "1 1", True),
            tc("1\n5\n3", "-1 -1", True),
            tc("10\n4 4 4 4 4 4 4 4 4 4\n4", "1 10", True),
            tc("11\n1 2 3 4 5 5 5 6 7 8 9\n5", "5 7", True),
        ],
        "templates": {
            "python": {
                "starter": """class Solution:
    def searchRange(self, arr, target):
        # arr is sorted in non-decreasing order and may contain duplicates.
        # Return a list [first, last] with 1-based indices of the first and
        # last occurrence of target, or [-1, -1] if target is not present.
        # TODO: implement using binary search (O(log n))
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
    result = sol.searchRange(arr, target)
    print(result[0], result[1])

if __name__ == "__main__":
    main()
""",
                "solution": """class Solution:
    def searchRange(self, arr, target):
        def find_bound(is_first):
            lo, hi = 0, len(arr) - 1
            result = -1
            while lo <= hi:
                mid = (lo + hi) // 2
                if arr[mid] == target:
                    result = mid
                    if is_first:
                        hi = mid - 1
                    else:
                        lo = mid + 1
                elif arr[mid] < target:
                    lo = mid + 1
                else:
                    hi = mid - 1
            return result

        first = find_bound(True)
        if first == -1:
            return [-1, -1]
        last = find_bound(False)
        return [first + 1, last + 1]
""",
            },
            "cpp": {
                "starter": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    vector<int> searchRange(vector<int>& arr, int target) {
        // arr is sorted in non-decreasing order and may contain duplicates.
        // Return {first, last} with 1-based indices of the first and last
        // occurrence of target, or {-1, -1} if target is not present.
        // TODO: implement using binary search (O(log n))
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
    vector<int> result = sol.searchRange(arr, target);
    cout << result[0] << " " << result[1] << endl;
    return 0;
}
""",
                "solution": """#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    vector<int> searchRange(vector<int>& arr, int target) {
        int first = findBound(arr, target, true);
        if (first == -1) return {-1, -1};
        int last = findBound(arr, target, false);
        return {first + 1, last + 1};
    }

private:
    int findBound(vector<int>& arr, int target, bool isFirst) {
        int lo = 0, hi = (int)arr.size() - 1, result = -1;
        while (lo <= hi) {
            int mid = lo + (hi - lo) / 2;
            if (arr[mid] == target) {
                result = mid;
                if (isFirst) hi = mid - 1;
                else lo = mid + 1;
            } else if (arr[mid] < target) {
                lo = mid + 1;
            } else {
                hi = mid - 1;
            }
        }
        return result;
    }
};
""",
            },
            "java": {
                "starter": """class Solution {
    public int[] searchRange(int[] arr, int target) {
        // arr is sorted in non-decreasing order and may contain duplicates.
        // Return {first, last} with 1-based indices of the first and last
        // occurrence of target, or {-1, -1} if target is not present.
        // TODO: implement using binary search (O(log n))
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
        int[] result = sol.searchRange(arr, target);
        System.out.println(result[0] + " " + result[1]);
    }
}
""",
                "solution": """class Solution {
    public int[] searchRange(int[] arr, int target) {
        int first = findBound(arr, target, true);
        if (first == -1) return new int[]{-1, -1};
        int last = findBound(arr, target, false);
        return new int[]{first + 1, last + 1};
    }

    private int findBound(int[] arr, int target, boolean isFirst) {
        int lo = 0, hi = arr.length - 1, result = -1;
        while (lo <= hi) {
            int mid = lo + (hi - lo) / 2;
            if (arr[mid] == target) {
                result = mid;
                if (isFirst) hi = mid - 1;
                else lo = mid + 1;
            } else if (arr[mid] < target) {
                lo = mid + 1;
            } else {
                hi = mid - 1;
            }
        }
        return result;
    }
}
""",
            },
        },
    },
]
