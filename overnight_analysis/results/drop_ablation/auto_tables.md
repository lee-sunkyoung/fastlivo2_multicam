## 자동 생성 표 — drop ablation (mainlab, both)

| 조건 | forced 파라미터 | n | 발산 | 실제 총 드롭률 | 자연 드롭(old/stale/ovf) | 인위 드롭 | 겹침 오차 p90 [m] | 겹침 오차 median [m] | 끝점→1회차 [m] | z 최대 이탈 [m] | 5회 편차 RMS [m] | 기준(both) 평균 궤적까지 RMS [m] | (참고) 시작~끝 3D [m] |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| both | 0.0 | 10 | 0 | 20.7 ± 0.9 % | 20.7 ± 0.9 % | 0.0 ± 0.0 % | 1.396 ± 1.264 | 0.499 ± 0.689 | 2.255 ± 2.381 | 1.151 ± 0.595 | 1.771 ± 1.422 | 1.771 ± 1.422 | 17.086 ± 4.122 |
| both_drop20 | 0.2 | 5 | 0 | 33.9 ± 1.1 % | 17.7 ± 1.2 % | 16.2 ± 0.2 % | 3.573 ± 2.766 | 0.871 ± 1.151 | 4.855 ± 2.221 | 0.770 ± 0.303 | 2.674 ± 1.343 | 2.658 ± 2.456 | 14.115 ± 2.952 |
| both_drop50 | 0.5 | 5 | 0 | 57.5 ± 0.7 % | 15.8 ± 1.0 % | 41.7 ± 0.5 % | 8.621 ± 5.731 | 2.634 ± 1.571 | 1.309 ± 0.809 | 0.613 ± 0.179 | 9.380 ± 6.858 | 14.097 ± 10.398 | 12.766 ± 9.482 |

런별 (총 드롭률 %, 겹침 p90 m, 기준 평균까지 RMS m): mainlab_both_1: (21.6, 0.48, 1.66); mainlab_both_2: (21.3, 0.37, 1.58); mainlab_both_3: (19.6, 1.38, 0.61); mainlab_both_4: (21.3, 0.42, 1.55); mainlab_both_5: (21.4, 0.37, 1.59); mainlab_both_6: (21.1, 4.07, 5.78); mainlab_both_7: (21.1, 0.37, 1.66); mainlab_both_8: (18.8, 1.99, 0.41); mainlab_both_9: (20.0, 1.25, 0.89); mainlab_both_10: (20.5, 3.27, 1.99); mainlab_both_drop20_1: (32.9, 0.86, 0.72); mainlab_both_drop20_2: (33.3, 0.99, 0.61); mainlab_both_drop20_3: (33.3, 8.40, 7.27); mainlab_both_drop20_4: (33.8, 4.44, 2.98); mainlab_both_drop20_5: (36.0, 3.18, 1.71); mainlab_both_drop50_1: (57.5, 14.45, 12.78); mainlab_both_drop50_2: (58.8, 2.99, 5.80); mainlab_both_drop50_3: (57.1, nan, 34.29); mainlab_both_drop50_4: (57.6, 2.79, 7.05); mainlab_both_drop50_5: (56.7, 14.25, 10.56)

추세 검정 (모든 런, x=실제 총 드롭률):

- drift: Spearman ρ=-0.32 (p=0.173), Kendall τ=-0.22 (p=0.186); 그룹 평균 순서 [17.086, 14.115, 12.766] → 단조 증가: False
- drift_xy: Spearman ρ=-0.33 (p=0.160), Kendall τ=-0.24 (p=0.146); 그룹 평균 순서 [17.042, 14.099, 12.765] → 단조 증가: False
- overlap_p90: Spearman ρ=0.43 (p=0.067), Kendall τ=0.30 (p=0.080); 그룹 평균 순서 [1.396, 3.573, 8.621] → 단조 증가: True
- overlap_med: Spearman ρ=0.40 (p=0.090), Kendall τ=0.27 (p=0.108); 그룹 평균 순서 [0.499, 0.871, 2.634] → 단조 증가: True
- end_to_loop1: Spearman ρ=-0.09 (p=0.700), Kendall τ=-0.05 (p=0.783); 그룹 평균 순서 [2.255, 4.855, 1.309] → 단조 증가: False
- z_absmax: Spearman ρ=-0.40 (p=0.088), Kendall τ=-0.30 (p=0.080); 그룹 평균 순서 [1.151, 0.77, 0.613] → 단조 증가: False
- rms_dev: Spearman ρ=0.60 (p=0.005), Kendall τ=0.47 (p=0.003); 그룹 평균 순서 [1.771, 2.674, 9.38] → 단조 증가: True
- rms_to_base_mean: Spearman ρ=0.72 (p=0.000), Kendall τ=0.52 (p=0.001); 그룹 평균 순서 [1.771, 2.658, 14.097] → 단조 증가: True

그림: `/home/lsk/dlr_ws/results/drop_ablation/ablation.png`, `/home/lsk/dlr_ws/results/drop_ablation/drop_composition.png`
