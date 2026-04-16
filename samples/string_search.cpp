// Naive brute-force string search — memory access pattern optimization candidate
#include <iostream>
#include <string>
using namespace std;

int naiveSearch(const string& text, const string& pattern) {
    int count = 0;
    int n = text.length();
    int m = pattern.length();
    for (int i = 0; i <= n - m; i++) {
        int j;
        for (j = 0; j < m; j++) {
            if (text[i + j] != pattern[j])
                break;
        }
        if (j == m) count++;
    }
    return count;
}

int main() {
    string text, pattern;
    cin >> text >> pattern;
    cout << naiveSearch(text, pattern) << endl;
    return 0;
}
