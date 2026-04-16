// Recursive power function — recursive → iterative candidate
#include <iostream>
using namespace std;

long long power(long long base, int exp) {
    if (exp == 0) return 1;
    if (exp == 1) return base;
    return base * power(base, exp - 1);
}

int main() {
    long long b;
    int e;
    cin >> b >> e;
    cout << power(b, e) << endl;
    return 0;
}
