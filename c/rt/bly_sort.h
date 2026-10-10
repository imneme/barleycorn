/* bly_sort.h: an in-place heapsort for one element kind. Define G_T (the C type) and G_X (its kind: the sort is
 * bly_sort_<X>, and it orders by bly_cmp_<X>), then include. Equal elements are identical values in Barley (records
 * compare every field), so the sort needn't be stable. */
#define CMP BLY_CAT(bly_cmp_, G_X)
static void BLY_CAT(bly_sift_, G_X)(G_T *a, u32 i, u32 n) {
    for (;;) {
        u32 c = 2 * i + 1;
        if (c >= n) return;
        if (c + 1 < n && CMP(a[c + 1], a[c]) > 0) c++;
        if (CMP(a[c], a[i]) <= 0) return;
        G_T t = a[i]; a[i] = a[c]; a[c] = t;
        i = c;
    }
}
static void BLY_CAT(bly_sort_, G_X)(G_T *a, u32 n) {
    for (u32 i = n / 2; i-- > 0;) BLY_CAT(bly_sift_, G_X)(a, i, n);
    for (u32 m = n; m > 1; m--) {
        G_T t = a[0]; a[0] = a[m - 1]; a[m - 1] = t;
        BLY_CAT(bly_sift_, G_X)(a, 0, m - 1);
    }
}
#undef CMP
#undef G_T
#undef G_X
