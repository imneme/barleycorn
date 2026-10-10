/* bly_map.h: map[K, V] and set[K]. Entries live in a dense array in insertion order (which is the order for walks
 * them in), beside an open-addressed index of entry numbers (-1 empty, -2 deleted), at most half full. Define G_NAME,
 * G_K, G_KX (the key's kind: bly_eq_, bly_hash_, bly_pr_), G_V and G_KIND ("map" or "set"). */
#define F(x) BLY_CAT(G_NAME, x)
#define KEQ BLY_CAT(bly_eq_, G_KX)
#define KHASH BLY_CAT(bly_hash_, G_KX)
#define KPR BLY_CAT(bly_pr_, G_KX)
typedef struct G_NAME { u32 ne, live, cap, ver, mask; G_K *k; G_V *v; u8 *alive; i32 *ix; } G_NAME;
static G_NAME *F(_new)(i64 cap, int l) {
    G_NAME *x = (G_NAME *)bly_alloc(sizeof(G_NAME), l);
    x->cap = bly_capacity(cap, G_KIND, l);
    u32 size = 4;
    while (size < 2 * x->cap) size *= 2;
    x->mask = size - 1;
    x->k = (G_K *)bly_alloc(x->cap * sizeof(G_K), l);
    x->v = (G_V *)bly_alloc(x->cap * sizeof(G_V), l);
    x->alive = (u8 *)bly_alloc(x->cap, l);
    x->ix = (i32 *)bly_alloc(size * sizeof(i32), l);
    for (u32 i = 0; i < size; i++) x->ix[i] = -1;
    return x;
}
static i64 F(_slot)(G_NAME *x, G_K key) {               /* the index slot holding key, or -1 */
    u32 h = (u32)KHASH(key) & x->mask;
    while (x->ix[h] != -1) {
        if (x->ix[h] >= 0 && KEQ(x->k[x->ix[h]], key)) return h;
        h = (h + 1) & x->mask;
    }
    return -1;
}
static void F(_index)(G_NAME *x, u32 e) {
    u32 h = (u32)KHASH(x->k[e]) & x->mask;
    while (x->ix[h] >= 0) h = (h + 1) & x->mask;
    x->ix[h] = (i32)e;
}
static void F(_compact)(G_NAME *x) {                     /* drop deleted entries, keeping the order */
    u32 j = 0;
    for (u32 i = 0; i < x->ne; i++)
        if (x->alive[i]) { x->k[j] = x->k[i]; x->v[j] = x->v[i]; x->alive[j] = 1; j++; }
    for (u32 i = j; i < x->ne; i++) x->alive[i] = 0;
    x->ne = j;
    for (u32 i = 0; i <= x->mask; i++) x->ix[i] = -1;
    for (u32 i = 0; i < x->ne; i++) F(_index)(x, i);
}
static b8 F(_has)(G_NAME *x, G_K key) { return F(_slot)(x, key) >= 0; }
static void F(_put)(G_NAME *x, G_K key, G_V val, int l) {
    i64 s = F(_slot)(x, key);
    if (s >= 0) { x->v[x->ix[s]] = val; return; }
    if (x->live >= x->cap) { bly_pr_cstr(G_KIND " full ("); bly_pr_int(x->cap); bly_fail(")", l); }
    if (x->ne == x->cap) F(_compact)(x);
    u32 e = x->ne++;
    x->k[e] = key; x->v[e] = val; x->alive[e] = 1;
    F(_index)(x, e);
    x->live++;
    x->ver++;
}
_Noreturn static void F(_missing)(G_K key, int l) { bly_pr_cstr("no key "); KPR(key); bly_fail(" in the map", l); }
static G_V F(_get)(G_NAME *x, G_K key, int l) {
    i64 s = F(_slot)(x, key);
    if (s < 0) F(_missing)(key, l);
    return x->v[x->ix[s]];
}
static G_V *F(_ref)(G_NAME *x, G_K key, int l) {
    i64 s = F(_slot)(x, key);
    if (s < 0) F(_missing)(key, l);
    return &x->v[x->ix[s]];
}
static G_V F(_getd)(G_NAME *x, G_K key, G_V d) { i64 s = F(_slot)(x, key); return s < 0 ? d : x->v[x->ix[s]]; }
static void F(_del)(G_NAME *x, G_K key) {
    i64 s = F(_slot)(x, key);
    if (s < 0) return;
    x->alive[x->ix[s]] = 0;
    x->ix[s] = -2;
    x->live--;
    x->ver++;
}
#undef KEQ
#undef KHASH
#undef KPR
#undef F
#undef G_NAME
#undef G_K
#undef G_KX
#undef G_V
#undef G_KIND
